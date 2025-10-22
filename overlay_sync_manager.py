#!/usr/bin/env python3
"""
Hikvision Overlay Sync Manager

Automatically synchronizes text overlays to Hikvision cameras at configurable intervals.
Based on the logic from example_update_overlay.py with added scheduling, configuration
management, dynamic templates, and robust error handling.

Usage:
    overlay_sync_manager.py config.json              # Start daemon
    overlay_sync_manager.py --validate config.json   # Validate configuration
    overlay_sync_manager.py --once config.json       # Run single sync cycle
"""

import argparse
import asyncio
import json
import logging
import math
import signal
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import httpx
import requests
import urllib3
from requests.auth import HTTPDigestAuth

# Suppress SSL warnings for cameras with self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================================
# Configuration Data Classes (T004, T005, T006)
# ============================================================================


@dataclass
class OverlayConfig:
    """
    Configuration for a single text overlay.

    Attributes:
        id: Overlay ID (typically "1"-"8" on Hikvision cameras)
        content: Text content or template with {placeholders}
        enabled: Whether to enable this overlay on the camera
        position_x: X position in pixels (None to keep current)
        position_y: Y position in pixels (None to keep current)
    """

    id: str
    content: str
    enabled: bool = True
    position_x: Optional[int] = None
    position_y: Optional[int] = None


@dataclass
class CameraConfig:
    """
    Configuration for a single Hikvision camera.

    Attributes:
        name: Human-readable camera identifier (used in logs)
        ip: Camera IP address or hostname
        port: Camera HTTP port
        username: Camera admin username
        password: Camera admin password
        channel: Video channel number
        overlays: List of overlay definitions for this camera
    """

    name: str
    ip: str
    username: str
    password: str
    overlays: List[OverlayConfig]
    port: int = 80
    channel: int = 1


@dataclass
class ConfigurationRoot:
    """
    Top-level configuration object.

    Attributes:
        sync_interval: Seconds between sync cycles
        cameras: List of camera configurations
        timeout: HTTP request timeout in seconds
        log_level: Python logging level (DEBUG, INFO, WARNING, ERROR)
        fast_mode: Skip GET requests and use minimal XML (faster but skips position updates)
        stats_interval: Seconds between statistics reports (None to disable, 0 for auto)
    """

    sync_interval: int
    cameras: List[CameraConfig]
    timeout: int = 10
    log_level: str = "INFO"
    fast_mode: bool = True  # Enable by default for better performance
    stats_interval: Optional[int] = None  # None = disabled, 0 = auto, >0 = explicit interval


@dataclass
class TemplateContext:
    """
    Runtime data context for rendering dynamic overlay content.

    Attributes:
        timestamp: Current timestamp in format "YYYY-MM-DD HH:MM:SS"
        date: Current date "YYYY-MM-DD"
        time: Current time "HH:MM:SS"
        camera_name: Camera name from config
        overlay_id: Overlay ID being rendered
    """

    timestamp: str
    date: str
    time: str
    camera_name: str
    overlay_id: str


# ============================================================================
# Configuration Loading and Validation (T007, T008)
# ============================================================================


def load_config(config_path: Path) -> ConfigurationRoot:
    """
    Load and parse JSON configuration file.

    Args:
        config_path: Path to JSON configuration file

    Returns:
        Parsed ConfigurationRoot object

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If JSON is invalid
        KeyError: If required fields are missing
    """
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Parse overlays for each camera
    cameras = []
    for cam_data in data["cameras"]:
        overlays = [
            OverlayConfig(
                id=ov["id"],
                content=ov["content"],
                enabled=ov.get("enabled", True),
                position_x=ov.get("position_x"),
                position_y=ov.get("position_y"),
            )
            for ov in cam_data["overlays"]
        ]

        camera = CameraConfig(
            name=cam_data["name"],
            ip=cam_data["ip"],
            username=cam_data["username"],
            password=cam_data["password"],
            overlays=overlays,
            port=cam_data.get("port", 80),
            channel=cam_data.get("channel", 1),
        )
        cameras.append(camera)

    # Create root configuration
    config = ConfigurationRoot(
        sync_interval=data["sync_interval"],
        cameras=cameras,
        timeout=data.get("timeout", 10),
        log_level=data.get("log_level", "INFO"),
        fast_mode=data.get("fast_mode", True),
        stats_interval=data.get("stats_interval"),
    )

    return config


def validate_config(config: ConfigurationRoot) -> tuple[bool, List[str]]:
    """
    Validate configuration according to rules from data-model.md.

    Args:
        config: Configuration to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Validate sync_interval
    if config.sync_interval <= 0:
        errors.append(f"sync_interval must be > 0, got: {config.sync_interval}")

    # Validate timeout
    if config.timeout <= 0:
        errors.append(f"timeout must be > 0, got: {config.timeout}")

    # Warn if timeout > sync_interval
    if config.timeout > config.sync_interval:
        logging.warning(
            f"timeout ({config.timeout}s) is greater than sync_interval ({config.sync_interval}s). "
            f"This may cause overlapping sync cycles."
        )

    # Validate log_level
    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.log_level not in valid_log_levels:
        errors.append(
            f"log_level must be one of {valid_log_levels}, got: '{config.log_level}'"
        )

    # Validate cameras
    if not config.cameras:
        errors.append("cameras list must not be empty")

    # Check for unique camera names
    camera_names = [cam.name for cam in config.cameras]
    if len(camera_names) != len(set(camera_names)):
        duplicates = [name for name in camera_names if camera_names.count(name) > 1]
        errors.append(f"Duplicate camera names found: {set(duplicates)}")

    # Validate each camera
    for camera in config.cameras:
        # Check required fields
        if not camera.name:
            errors.append("Camera name must not be empty")
        if not camera.ip:
            errors.append(f"Camera '{camera.name}': IP address must not be empty")
        if not camera.username:
            errors.append(f"Camera '{camera.name}': username must not be empty")
        if not camera.password:
            errors.append(f"Camera '{camera.name}': password must not be empty")

        # Validate port
        if not (1 <= camera.port <= 65535):
            errors.append(
                f"Camera '{camera.name}': port must be 1-65535, got: {camera.port}"
            )

        # Validate channel
        if camera.channel < 1:
            errors.append(
                f"Camera '{camera.name}': channel must be >= 1, got: {camera.channel}"
            )

        # Validate overlays
        if not camera.overlays:
            errors.append(f"Camera '{camera.name}': overlays list must not be empty")

        # Check for unique overlay IDs within camera
        overlay_ids = [ov.id for ov in camera.overlays]
        if len(overlay_ids) != len(set(overlay_ids)):
            duplicates = [oid for oid in overlay_ids if overlay_ids.count(oid) > 1]
            errors.append(
                f"Camera '{camera.name}': Duplicate overlay IDs found: {set(duplicates)}"
            )

        # Validate each overlay
        for overlay in camera.overlays:
            if not overlay.id:
                errors.append(f"Camera '{camera.name}': overlay ID must not be empty")
            if not overlay.content:
                errors.append(
                    f"Camera '{camera.name}', overlay '{overlay.id}': "
                    f"content must not be empty"
                )

            # Check position values
            if overlay.position_x is not None and overlay.position_x < 0:
                errors.append(
                    f"Camera '{camera.name}', overlay '{overlay.id}': "
                    f"position_x must be >= 0, got: {overlay.position_x}"
                )
            if overlay.position_y is not None and overlay.position_y < 0:
                errors.append(
                    f"Camera '{camera.name}', overlay '{overlay.id}': "
                    f"position_y must be >= 0, got: {overlay.position_y}"
                )

    is_valid = len(errors) == 0
    return is_valid, errors


# ============================================================================
# Logging Setup (T009)
# ============================================================================


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure Python logging with format from research.md.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce httpx logging noise (hide digest auth 401 challenges)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ============================================================================
# HikvisionOverlay Client (T010 - adapted from example_update_overlay.py)
# ============================================================================


class HikvisionOverlayAsync:
    """
    Async client for interacting with Hikvision camera ISAPI text overlay endpoints.
    Uses httpx for non-blocking concurrent requests with digest auth support.

    Optimized for persistent connections across multiple sync cycles.
    """

    # Pre-compiled XML template for performance
    _XML_TEMPLATE = '<?xml version="1.0" encoding="UTF-8"?>\n<TextOverlay version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">\n    <id>{}</id>\n    <enabled>{}</enabled>\n    <displayText>{}</displayText>\n</TextOverlay>'

    def __init__(self, ip: str, username: str, password: str, channel: int = 1):
        """
        Initialize async Hikvision Overlay client.

        Args:
            ip: Camera IP address with optional port
            username: Camera username
            password: Camera password
            channel: Video channel number (default: 1)
        """
        self.ip = ip
        self.username = username
        self.password = password
        self.channel = channel

        # Add port if not specified
        if ":" not in self.ip:
            self.ip = f"{self.ip}:80"

        # Create persistent async client (will be initialized in context manager)
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        # Create httpx client with digest auth
        self._client = httpx.AsyncClient(
            auth=httpx.DigestAuth(self.username, self.password),
            verify=False,
            timeout=30.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def initialize(self):
        """Initialize the async client for persistent use. Call once at startup."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=httpx.DigestAuth(self.username, self.password),
                verify=False,
                timeout=30.0,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )

    async def close(self):
        """Close the async client. Call at shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def update_overlay_text_fast(
        self,
        overlay_id: str,
        new_text: str,
        enable: bool = True,
        timeout: int = 10,
    ) -> bool:
        """
        Fast async update that uses minimal XML template.

        Args:
            overlay_id: Overlay ID
            new_text: New text to display
            enable: Enable the overlay if True
            timeout: Request timeout in seconds

        Returns:
            True on success, False on error
        """
        # Use pre-compiled template for faster XML generation
        xml_content = self._XML_TEMPLATE.format(
            overlay_id, "true" if enable else "false", new_text
        )

        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays/text/{overlay_id}"

        try:
            response = await self._client.put(
                url,
                content=xml_content,
                headers={"Content-Type": "application/xml"},
                timeout=timeout,
            )
            response.raise_for_status()
            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # 401 after digest auth means wrong credentials
                logging.error(
                    f"Authentication failed for overlay {overlay_id} - check credentials"
                )
            else:
                logging.error(
                    f"HTTP {e.response.status_code} updating overlay {overlay_id}: {e}"
                )
            return False
        except Exception as e:
            logging.debug(f"Error updating overlay (async fast mode): {e}")
            return False


class HikvisionOverlay:
    """
    Client for interacting with Hikvision camera ISAPI text overlay endpoints.

    Adapted from example_update_overlay.py with minimal changes for integration.
    """

    def __init__(self, ip: str, username: str, password: str, channel: int = 1):
        """
        Initialize Hikvision Overlay client.

        Args:
            ip: Camera IP address with optional port (e.g., "192.168.1.100" or "192.168.1.100:80")
            username: Camera username
            password: Camera password
            channel: Video channel number (default: 1)
        """
        self.ip = ip
        self.username = username
        self.password = password
        self.channel = channel
        self.auth = HTTPDigestAuth(username, password)
        self.screen_width = None
        self.screen_height = None

        # Add port if not specified
        if ":" not in self.ip:
            self.ip = f"{self.ip}:80"

        # Create persistent session for connection pooling (HTTP keep-alive)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.verify = False

    def get_overlay_text(
        self, overlay_id: str, timeout: int = 10
    ) -> Optional[ET.Element]:
        """
        Get current text overlay configuration.

        Args:
            overlay_id: Overlay ID (e.g., "1", "2", etc.)
            timeout: Request timeout in seconds

        Returns:
            XML Element tree of the overlay, or None on error
        """
        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays/text/{overlay_id}"

        try:
            response = self.session.get(
                url,
                headers={"Content-Type": "application/xml"},
                timeout=timeout,
            )
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)
            return root

        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting overlay: {e}")
            return None

    def update_overlay_text_fast(
        self,
        overlay_id: str,
        new_text: str,
        enable: bool = True,
        position_x: Optional[int] = None,
        position_y: Optional[int] = None,
        timeout: int = 10,
    ) -> bool:
        """
        Fast update that skips GET and uses cached XML template.
        Only works if overlay structure is known.

        Args:
            overlay_id: Overlay ID (e.g., "1", "2", etc.)
            new_text: New text to display
            enable: Enable the overlay if True
            position_x: X position in pixels (None to keep current)
            position_y: Y position in pixels (None to keep current)
            timeout: Request timeout in seconds

        Returns:
            True on success, False on error
        """
        # Build minimal XML directly without GET
        xml_template = f"""<?xml version="1.0" encoding="UTF-8"?>
<TextOverlay version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
    <id>{overlay_id}</id>
    <enabled>{"true" if enable else "false"}</enabled>
    <displayText>{new_text}</displayText>
</TextOverlay>"""

        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays/text/{overlay_id}"

        try:
            response = self.session.put(
                url,
                headers={"Content-Type": "application/xml"},
                data=xml_template,
                timeout=timeout,
            )
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Error updating overlay (fast mode): {e}")
            return False

    def update_overlay_text(
        self,
        overlay_id: str,
        new_text: str,
        enable: bool = True,
        position_x: Optional[int] = None,
        position_y: Optional[int] = None,
        timeout: int = 10,
    ) -> bool:
        """
        Update text overlay with new text.

        Args:
            overlay_id: Overlay ID (e.g., "1", "2", etc.)
            new_text: New text to display
            enable: Enable the overlay if True
            position_x: X position in pixels (None to keep current)
            position_y: Y position in pixels (None to keep current)
            timeout: Request timeout in seconds

        Returns:
            True on success, False on error
        """
        # First, get current overlay configuration
        overlay_xml = self.get_overlay_text(overlay_id, timeout)
        if overlay_xml is None:
            return False

        # Extract namespace if present
        ns = (
            {"ns": overlay_xml.tag.split("}")[0].strip("{")}
            if "}" in overlay_xml.tag
            else {}
        )

        # Register namespace to avoid ns0: prefix
        if ns:
            ET.register_namespace("", ns["ns"])

        # Update the displayText field
        display_text_elem = overlay_xml.find(
            "ns:displayText" if ns else "displayText", ns
        )
        if display_text_elem is not None:
            display_text_elem.text = new_text
        else:
            logging.error(
                f"Error: displayText element not found in overlay {overlay_id}"
            )
            return False

        # Enable overlay if requested
        if enable:
            enabled_elem = overlay_xml.find("ns:enabled" if ns else "enabled", ns)
            if enabled_elem is not None:
                enabled_elem.text = "true"

        # Update position if provided
        if position_x is not None:
            pos_x_elem = overlay_xml.find("ns:positionX" if ns else "positionX", ns)
            if pos_x_elem is not None:
                pos_x_elem.text = str(position_x)

        if position_y is not None:
            pos_y_elem = overlay_xml.find("ns:positionY" if ns else "positionY", ns)
            if pos_y_elem is not None:
                pos_y_elem.text = str(position_y)

        # Convert back to XML string
        xml_str = ET.tostring(overlay_xml, encoding="unicode", method="xml")

        # Send PUT request to update overlay
        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays/text/{overlay_id}"

        try:
            response = self.session.put(
                url,
                headers={"Content-Type": "application/xml"},
                data=xml_str,
                timeout=timeout,
            )
            response.raise_for_status()

            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Error updating overlay: {e}")
            return False


# ============================================================================
# Template Rendering (T029-T030: Dynamic Content Generation)
# ============================================================================


def create_template_context(camera_name: str, overlay_id: str) -> dict[str, str]:
    """
    Generate template context with current datetime values.

    Args:
        camera_name: Name of the camera from config
        overlay_id: ID of the overlay being rendered

    Returns:
        Dictionary with template variables
    """
    now = datetime.now()
    return {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "camera_name": camera_name,
        "overlay_id": overlay_id,
    }


def render_template(template: str, context: dict[str, str]) -> str:
    """
    Render template string using str.format() with provided context.

    Args:
        template: Template string with {placeholder} syntax
        context: Dictionary of template variables

    Returns:
        Rendered string with placeholders replaced

    Note:
        - Missing placeholders result in warnings and literal text preservation
        - Template rendering errors are logged and original template is returned
    """
    try:
        # Attempt to render the template
        rendered = template.format(**context)
        return rendered
    except KeyError as e:
        # T032: Warning for missing placeholder
        placeholder_name = str(e).strip("'\"")
        logging.warning(
            f"Template placeholder '{{{placeholder_name}}}' not found in context. "
            f"Available placeholders: {', '.join(f'{{{k}}}' for k in context.keys())}. "
            f"Using literal text."
        )
        # Return original template with literal braces
        return template
    except Exception as e:
        # T033: Fallback handling for complete rendering failure
        logging.error(f"Failed to render template: {e}. Using literal template string.")
        return template


# ============================================================================
# Connection Testing (T038: Startup Connection Test)
# ============================================================================


def test_camera_connection(camera: CameraConfig, timeout: int) -> bool:
    """
    Test if camera is reachable before starting sync loop.

    Args:
        camera: Camera configuration to test
        timeout: Connection timeout in seconds

    Returns:
        True if camera responds, False otherwise
    """
    try:
        client = HikvisionOverlay(
            ip=camera.ip if ":" not in camera.ip else camera.ip.split(":")[0],
            username=camera.username,
            password=camera.password,
            channel=camera.channel,
        )

        # Handle port if specified separately
        if camera.port != 80:
            client.ip = f"{camera.ip}:{camera.port}"
        elif ":" not in camera.ip:
            client.ip = f"{camera.ip}:80"

        # Try to get first overlay to test connection
        if camera.overlays:
            result = client.get_overlay_text(camera.overlays[0].id, timeout)
            return result is not None
        return False

    except Exception as e:
        logging.debug(f"Connection test failed for '{camera.name}': {e}")
        return False


def test_all_cameras(config: ConfigurationRoot) -> tuple[int, int]:
    """
    Test connection to all cameras before starting sync loop.

    Args:
        config: Configuration root object

    Returns:
        Tuple of (reachable_count, total_count)
    """
    reachable = 0
    total = len(config.cameras)

    logging.info("Testing camera connections...")
    for camera in config.cameras:
        if test_camera_connection(camera, config.timeout):
            logging.info(f"  ✓ Camera '{camera.name}' is reachable")
            reachable += 1
        else:
            logging.warning(f"  ✗ Camera '{camera.name}' is not reachable")

    return reachable, total


# ============================================================================
# Async Sync Functions (Non-blocking concurrent updates)
# ============================================================================


async def sync_overlay_async(
    client: HikvisionOverlayAsync,
    camera_name: str,
    overlay: OverlayConfig,
    timeout: int,
) -> bool:
    """
    Async sync a single overlay to the camera.

    Args:
        client: HikvisionOverlayAsync client instance
        camera_name: Camera name (for logging)
        overlay: Overlay configuration
        timeout: Request timeout in seconds

    Returns:
        True if sync succeeded, False otherwise
    """
    try:
        start_time = time.time()

        # Render template with dynamic context
        context = create_template_context(camera_name, overlay.id)
        content = render_template(overlay.content, context)

        # Validate overlay text length
        if len(content) > 44:
            logging.warning(
                f"Overlay text for '{camera_name}' overlay {overlay.id} truncated "
                f"from {len(content)} to 44 characters"
            )
            content = content[:44]

        # Use async fast mode
        success = await client.update_overlay_text_fast(
            overlay_id=overlay.id,
            new_text=content,
            enable=overlay.enabled,
            timeout=timeout,
        )

        duration = time.time() - start_time

        if success:
            content_preview = content[:30] + "..." if len(content) > 30 else content
            logging.info(
                f"✓ Updated overlay {overlay.id} on '{camera_name}': \"{content_preview}\" ({duration * 1000:.0f}ms)"
            )
        else:
            logging.error(
                f"✗ Failed to update overlay {overlay.id} on '{camera_name}' ({duration * 1000:.0f}ms)"
            )

        return success

    except Exception as e:
        logging.error(
            f"Unexpected error syncing overlay {overlay.id} on '{camera_name}': {e}"
        )
        return False


async def sync_camera_async(
    camera: CameraConfig,
    timeout: int,
    client: Optional[HikvisionOverlayAsync] = None,
) -> dict[str, Any]:
    """
    Async sync all overlays for a single camera.

    Args:
        camera: Camera configuration
        timeout: Request timeout in seconds
        client: Optional persistent client (if None, creates temporary client)

    Returns:
        Dictionary with 'success', 'failed' counts, and 'duration' in seconds
    """
    start_time = time.time()
    success_count = 0
    failed_count = 0

    # Use provided persistent client or create temporary one
    if client is not None:
        # Use persistent client (no context manager needed)
        tasks = [
            sync_overlay_async(client, camera.name, overlay, timeout)
            for overlay in camera.overlays
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures
        for result in results:
            if isinstance(result, Exception):
                failed_count += 1
            elif result:
                success_count += 1
            else:
                failed_count += 1
    else:
        # Fallback: create temporary client with context manager
        async with HikvisionOverlayAsync(
            ip=camera.ip if ":" not in camera.ip else camera.ip.split(":")[0],
            username=camera.username,
            password=camera.password,
            channel=camera.channel,
        ) as temp_client:
            # Handle port
            if camera.port != 80:
                temp_client.ip = f"{camera.ip}:{camera.port}"
            elif ":" not in camera.ip:
                temp_client.ip = f"{camera.ip}:80"

            # Sync all overlays concurrently using asyncio.gather
            tasks = [
                sync_overlay_async(temp_client, camera.name, overlay, timeout)
                for overlay in camera.overlays
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes and failures
            for result in results:
                if isinstance(result, Exception):
                    failed_count += 1
                elif result:
                    success_count += 1
                else:
                    failed_count += 1

    duration = time.time() - start_time
    return {"success": success_count, "failed": failed_count, "duration": duration}


async def sync_all_cameras_async(
    config: ConfigurationRoot,
    clients: Optional[dict[str, HikvisionOverlayAsync]] = None,
) -> dict[str, Any]:
    """
    Async sync overlays for all cameras concurrently.

    Args:
        config: Configuration root object
        clients: Optional dict of persistent clients by camera name

    Returns:
        Dictionary with sync results for all cameras
    """
    # Sync all cameras concurrently
    if clients:
        # Use persistent clients
        tasks = [
            sync_camera_async(camera, config.timeout, clients.get(camera.name))
            for camera in config.cameras
        ]
    else:
        # Create temporary clients
        tasks = [sync_camera_async(camera, config.timeout) for camera in config.cameras]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_success = 0
    total_failed = 0
    camera_results = {}

    for i, camera in enumerate(config.cameras):
        result = results[i]
        if isinstance(result, Exception):
            logging.error(f"Failed to sync camera '{camera.name}': {result}")
            camera_results[camera.name] = {"success": 0, "failed": len(camera.overlays)}
            total_failed += len(camera.overlays)
        else:
            camera_results[camera.name] = result
            total_success += result["success"]
            total_failed += result["failed"]

    return {
        "total_success": total_success,
        "total_failed": total_failed,
        "cameras": camera_results,
    }


# ============================================================================
# Sync Functions (T018-T020: Core Sync Logic)
# ============================================================================


def sync_overlay(
    client: HikvisionOverlay,
    camera_name: str,
    overlay: OverlayConfig,
    timeout: int,
    fast_mode: bool = True,
) -> bool:
    """
    Sync a single overlay to the camera.

    Args:
        client: HikvisionOverlay client instance
        camera_name: Camera name (for logging)
        overlay: Overlay configuration
        timeout: Request timeout in seconds

    Returns:
        True if sync succeeded, False otherwise
    """
    try:
        # T031: Render template with dynamic context
        context = create_template_context(camera_name, overlay.id)
        content = render_template(overlay.content, context)

        # T039: Validate overlay text length (Hikvision limit is 44 chars)
        if len(content) > 44:
            logging.warning(
                f"Overlay text for '{camera_name}' overlay {overlay.id} truncated "
                f"from {len(content)} to 44 characters"
            )
            content = content[:44]

        # Use fast mode if enabled (skips GET, 2x faster)
        if fast_mode and overlay.position_x is None and overlay.position_y is None:
            success = client.update_overlay_text_fast(
                overlay_id=overlay.id,
                new_text=content,
                enable=overlay.enabled,
                timeout=timeout,
            )
        else:
            # Fallback to full mode if position updates needed
            success = client.update_overlay_text(
                overlay_id=overlay.id,
                new_text=content,
                enable=overlay.enabled,
                position_x=overlay.position_x,
                position_y=overlay.position_y,
                timeout=timeout,
            )

        if success:
            # T025: Per-overlay success logging
            content_preview = content[:30] + "..." if len(content) > 30 else content
            logging.info(
                f"✓ Updated overlay {overlay.id} on '{camera_name}': \"{content_preview}\""
            )
        else:
            logging.error(f"✗ Failed to update overlay {overlay.id} on '{camera_name}'")

        return success

    except requests.exceptions.HTTPError as e:
        # T035: Specific handling for HTTP auth errors
        if e.response is not None and e.response.status_code in (401, 403):
            logging.error(
                f"Authentication failed for camera '{camera_name}'. "
                f"Check username/password in config. Error: {e}"
            )
        else:
            logging.error(
                f"HTTP error syncing overlay {overlay.id} on '{camera_name}': {e}. "
                f"Will retry on next cycle."
            )
        return False

    except requests.exceptions.Timeout as e:
        # T036: Timeout handling
        logging.error(
            f"Timeout ({timeout}s) syncing overlay {overlay.id} on '{camera_name}': {e}. "
            f"Will retry on next cycle."
        )
        return False

    except requests.exceptions.RequestException as e:
        # T034: General network error handling
        logging.error(
            f"Failed to sync overlay {overlay.id} on '{camera_name}': {e}. "
            f"Will retry on next cycle."
        )
        return False

    except ET.ParseError as e:
        # T040: XML parsing error handling
        logging.error(
            f"XML parsing error for overlay {overlay.id} on '{camera_name}'. "
            f"Camera returned unexpected XML format: {e}. Skipping this overlay."
        )
        return False

    except Exception as e:
        # Catch-all for unexpected errors
        logging.error(
            f"Unexpected error syncing overlay {overlay.id} on '{camera_name}': {e}. "
            f"Will retry on next cycle."
        )
        return False


def sync_camera(camera: CameraConfig, timeout: int) -> dict[str, int]:
    """
    Sync all overlays for a single camera.

    Args:
        camera: Camera configuration
        timeout: Request timeout in seconds

    Returns:
        Dictionary with 'success' and 'failed' counts
    """
    # Create camera client
    client = HikvisionOverlay(
        ip=camera.ip if ":" not in camera.ip else camera.ip.split(":")[0],
        username=camera.username,
        password=camera.password,
        channel=camera.channel,
    )

    # Handle port if specified separately
    if camera.port != 80:
        client.ip = f"{camera.ip}:{camera.port}"
    elif ":" not in camera.ip:
        client.ip = f"{camera.ip}:80"

    success_count = 0
    failed_count = 0

    # T019: Sync each overlay with per-overlay error handling
    for overlay in camera.overlays:
        try:
            if sync_overlay(client, camera.name, overlay, timeout):
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logging.error(
                f"Unexpected error syncing overlay {overlay.id} on '{camera.name}': {e}"
            )
            failed_count += 1

    return {"success": success_count, "failed": failed_count}


def sync_all_cameras(config: ConfigurationRoot) -> dict[str, Any]:
    """
    Sync overlays for all configured cameras.

    Args:
        config: Configuration root object

    Returns:
        Dictionary with sync results for all cameras
    """
    total_success = 0
    total_failed = 0
    camera_results = {}

    # T020: Sync each camera with per-camera error isolation
    for camera in config.cameras:
        try:
            results = sync_camera(camera, config.timeout)
            total_success += results["success"]
            total_failed += results["failed"]
            camera_results[camera.name] = results
        except Exception as e:
            logging.error(
                f"Failed to sync camera '{camera.name}': {e}. Will retry on next cycle."
            )
            camera_results[camera.name] = {"success": 0, "failed": len(camera.overlays)}
            total_failed += len(camera.overlays)

    return {
        "total_success": total_success,
        "total_failed": total_failed,
        "cameras": camera_results,
    }


# ============================================================================
# SyncManager Class (T021-T026: Daemon Loop & Signal Handling)
# ============================================================================


class SyncManager:
    """
    Manages periodic synchronization of camera overlays.

    Optimized with persistent async clients and event loop for maximum performance.
    """

    def __init__(self, config: ConfigurationRoot):
        """
        Initialize SyncManager.

        Args:
            config: Configuration root object
        """
        self.config = config
        self.running = False
        self.syncing = False  # T026: Track if sync in progress
        self.cycle_count = 0
        # Create persistent camera clients for connection reuse (sync fallback)
        self.camera_clients = self._create_camera_clients()
        # Create persistent async clients (for optimized async path)
        self.async_clients: Optional[dict[str, HikvisionOverlayAsync]] = None
        # Event loop for async operations
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Runtime statistics tracking
        self.start_time: Optional[float] = None
        self.last_stats_time: Optional[float] = None

        # Calculate stats interval: None = disabled, 0 = auto (min(60, sync_interval)), >0 = explicit
        if config.stats_interval is None:
            self.stats_interval: Optional[float] = None  # Disabled
        elif config.stats_interval == 0:
            self.stats_interval = min(60.0, self.config.sync_interval)  # Auto
        else:
            self.stats_interval = float(config.stats_interval)  # Explicit

        # Rolling window statistics (prevents overflow for year-round operation)
        # Keep last N cycles for accurate recent statistics
        self.stats_window_size = 10000  # ~2.7 hours at 1s interval, ~3 days at 30s
        self.recent_success: list[int] = []
        self.recent_failed: list[int] = []
        self.sync_times: list[float] = []  # Sync durations

        # Lifetime counters (use for uptime display only, not averages)
        self.total_success_count = 0
        self.total_failed_count = 0

        # Min/max tracking
        self.min_sync_time: Optional[float] = None
        self.max_sync_time: Optional[float] = None

        # Per-camera statistics (also rolling window)
        self.camera_stats: dict[str, dict[str, Any]] = {
            camera.name: {
                "recent_success": [],  # Rolling window
                "recent_failed": [],   # Rolling window
                "recent_times": [],    # Rolling window of sync times
                "total_overlays": len(camera.overlays),
                "lifetime_success": 0,  # For display only
                "lifetime_failed": 0,   # For display only
            }
            for camera in config.cameras
        }

    def _create_camera_clients(self) -> dict[str, HikvisionOverlay]:
        """
        Create persistent HikvisionOverlay clients for each camera.
        Reusing clients allows HTTP connection pooling.

        Returns:
            Dictionary mapping camera name to HikvisionOverlay client
        """
        clients = {}
        for camera in self.config.cameras:
            client = HikvisionOverlay(
                ip=camera.ip if ":" not in camera.ip else camera.ip.split(":")[0],
                username=camera.username,
                password=camera.password,
                channel=camera.channel,
            )

            # Handle port if specified separately
            if camera.port != 80:
                client.ip = f"{camera.ip}:{camera.port}"
            elif ":" not in camera.ip:
                client.ip = f"{camera.ip}:80"

            clients[camera.name] = client

        return clients

    async def _create_async_clients(self) -> dict[str, HikvisionOverlayAsync]:
        """
        Create persistent async clients for each camera.
        These clients persist across sync cycles for maximum performance.

        Returns:
            Dictionary mapping camera name to HikvisionOverlayAsync client
        """
        clients = {}
        for camera in self.config.cameras:
            client = HikvisionOverlayAsync(
                ip=camera.ip if ":" not in camera.ip else camera.ip.split(":")[0],
                username=camera.username,
                password=camera.password,
                channel=camera.channel,
            )

            # Handle port if specified separately
            if camera.port != 80:
                client.ip = f"{camera.ip}:{camera.port}"
            elif ":" not in camera.ip:
                client.ip = f"{camera.ip}:80"

            # Initialize the client
            await client.initialize()
            clients[camera.name] = client

        return clients

    async def _close_async_clients(self):
        """Close all persistent async clients."""
        if self.async_clients:
            for client in self.async_clients.values():
                await client.close()
            self.async_clients = None

    def _update_statistics(
        self,
        duration: float,
        success_count: int,
        failed_count: int,
        camera_results: dict[str, dict[str, int]],
    ):
        """
        Update runtime statistics with sync cycle results.
        Uses rolling windows to prevent overflow during year-round operation.

        Args:
            duration: Sync cycle duration in seconds
            success_count: Number of successful overlay updates
            failed_count: Number of failed overlay updates
            camera_results: Per-camera results dict with success/failed counts
        """
        # Update lifetime counters (for display only)
        self.total_success_count += success_count
        self.total_failed_count += failed_count

        # Track min/max sync times
        if self.min_sync_time is None or duration < self.min_sync_time:
            self.min_sync_time = duration
        if self.max_sync_time is None or duration > self.max_sync_time:
            self.max_sync_time = duration

        # Rolling window for recent statistics
        self.recent_success.append(success_count)
        self.recent_failed.append(failed_count)
        self.sync_times.append(duration)

        # Maintain window size
        if len(self.recent_success) > self.stats_window_size:
            self.recent_success.pop(0)
        if len(self.recent_failed) > self.stats_window_size:
            self.recent_failed.pop(0)
        if len(self.sync_times) > self.stats_window_size:
            self.sync_times.pop(0)

        # Update per-camera statistics (rolling windows)
        for camera_name, results in camera_results.items():
            if camera_name in self.camera_stats:
                stats = self.camera_stats[camera_name]

                # Lifetime counters
                stats["lifetime_success"] += results.get("success", 0)
                stats["lifetime_failed"] += results.get("failed", 0)

                # Rolling windows
                stats["recent_success"].append(results.get("success", 0))
                stats["recent_failed"].append(results.get("failed", 0))
                stats["recent_times"].append(results.get("duration", 0.0))

                # Maintain window size
                if len(stats["recent_success"]) > self.stats_window_size:
                    stats["recent_success"].pop(0)
                if len(stats["recent_failed"]) > self.stats_window_size:
                    stats["recent_failed"].pop(0)
                if len(stats["recent_times"]) > self.stats_window_size:
                    stats["recent_times"].pop(0)

    def _format_uptime(self, seconds: float) -> str:
        """
        Format uptime in human-readable format.

        Args:
            seconds: Uptime in seconds

        Returns:
            Formatted string (e.g., "2h 15m 30s" or "45m 12s" or "23s")
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def _print_statistics(self):
        """Print runtime statistics summary."""
        if self.start_time is None:
            return

        current_time = time.time()
        uptime = current_time - self.start_time

        # Use rolling window for recent statistics
        window_success = sum(self.recent_success) if self.recent_success else 0
        window_failed = sum(self.recent_failed) if self.recent_failed else 0
        window_total = window_success + window_failed

        # Calculate success rate from rolling window
        success_rate = (
            (window_success / window_total * 100) if window_total > 0 else 0.0
        )

        # Calculate average sync time from rolling window
        avg_sync_time = (
            sum(self.sync_times) / len(self.sync_times) if self.sync_times else 0.0
        )

        # Log statistics
        logging.info("=" * 70)
        logging.info("RUNTIME STATISTICS")
        logging.info("=" * 70)
        logging.info(f"Uptime:           {self._format_uptime(uptime)}")
        logging.info(f"Sync cycles:      {self.cycle_count}")
        logging.info(
            f"Window updates:   {window_total} ({window_success} success, {window_failed} failed)"
        )
        logging.info(
            f"Lifetime updates: {self.total_success_count + self.total_failed_count} "
            f"({self.total_success_count} success, {self.total_failed_count} failed)"
        )
        logging.info(f"Success rate:     {success_rate:.1f}% (window)")
        logging.info(f"Avg sync time:    {avg_sync_time * 1000:.0f}ms (window)")
        if self.min_sync_time is not None and self.max_sync_time is not None:
            logging.info(
                f"Min/Max sync:     {self.min_sync_time * 1000:.0f}ms / {self.max_sync_time * 1000:.0f}ms"
            )
        logging.info(
            f"Window size:      {len(self.sync_times)} cycles"
        )

        # Per-camera statistics
        logging.info("-" * 70)
        logging.info("PER-CAMERA STATISTICS")
        logging.info("-" * 70)
        for camera_name, stats in sorted(self.camera_stats.items()):
            # Use rolling window for calculations
            window_cam_success = sum(stats["recent_success"]) if stats["recent_success"] else 0
            window_cam_failed = sum(stats["recent_failed"]) if stats["recent_failed"] else 0
            window_cam_total = window_cam_success + window_cam_failed

            camera_success_rate = (
                (window_cam_success / window_cam_total * 100) if window_cam_total > 0 else 0.0
            )
            avg_camera_time = (
                sum(stats["recent_times"]) / len(stats["recent_times"])
                if stats["recent_times"] else 0.0
            )
            overlays_str = f"{stats['total_overlays']} overlay{'s' if stats['total_overlays'] != 1 else ''}"

            logging.info(
                f"  {camera_name:20s} {window_cam_success:6d} success, {window_cam_failed:6d} failed  "
                f"({camera_success_rate:5.1f}%)  avg: {avg_camera_time * 1000:4.0f}ms  [{overlays_str}]"
            )
        logging.info("=" * 70)

    def _sync_all_cameras_optimized(self) -> dict[str, Any]:
        """
        Sync overlays for all cameras using persistent clients for better performance.

        Returns:
            Dictionary with sync results
        """
        total_success = 0
        total_failed = 0
        camera_results = {}

        for camera in self.config.cameras:
            try:
                client = self.camera_clients[camera.name]
                success_count = 0
                failed_count = 0

                # Sync each overlay
                for overlay in camera.overlays:
                    try:
                        if sync_overlay(
                            client,
                            camera.name,
                            overlay,
                            self.config.timeout,
                            self.config.fast_mode,
                        ):
                            success_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        logging.error(
                            f"Unexpected error syncing overlay {overlay.id} on '{camera.name}': {e}"
                        )
                        failed_count += 1

                total_success += success_count
                total_failed += failed_count
                camera_results[camera.name] = {
                    "success": success_count,
                    "failed": failed_count,
                }

            except Exception as e:
                logging.error(
                    f"Failed to sync camera '{camera.name}': {e}. Will retry on next cycle."
                )
                camera_results[camera.name] = {
                    "success": 0,
                    "failed": len(camera.overlays),
                }
                total_failed += len(camera.overlays)

        return {
            "total_success": total_success,
            "total_failed": total_failed,
            "cameras": camera_results,
        }

    def _shutdown(self, signum, frame):
        """
        Signal handler for graceful shutdown.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_names = {signal.SIGINT: "SIGINT", signal.SIGTERM: "SIGTERM"}
        signal_name = signal_names.get(signum, f"signal {signum}")
        logging.info(f"Received interrupt signal ({signal_name})")
        logging.info("Shutting down gracefully...")
        self.running = False

    async def _run_async(self):
        """
        Async main loop - runs continuously with persistent event loop.
        This avoids asyncio.run() overhead on every cycle.
        """
        # Initialize runtime tracking
        self.start_time = time.time()
        self.last_stats_time = self.start_time

        # Create persistent async clients
        self.async_clients = await self._create_async_clients()
        logging.info(f"Initialized {len(self.async_clients)} persistent async clients")

        # Log statistics configuration
        if self.stats_interval is None:
            logging.info("Statistics reporting: disabled")
        else:
            logging.info(f"Statistics will be reported every {self.stats_interval:.0f}s")

        # T022: Main sync loop with precise timing
        # Align to exact second boundaries for zero drift

        # Wait until next exact second boundary to start
        current = time.time()
        # Round up to next second boundary
        if self.config.sync_interval >= 1:
            # For intervals >= 1s, align to exact seconds
            next_sync_time = math.ceil(current)
        else:
            # For sub-second intervals, align to interval boundaries
            next_sync_time = (
                math.ceil(current / self.config.sync_interval)
                * self.config.sync_interval
            )

        logging.info(
            f"Aligning to next boundary: {next_sync_time - current:.3f}s from now"
        )

        try:
            while self.running:
                # Wait until next scheduled sync time
                current_time = time.time()
                if current_time < next_sync_time:
                    sleep_time = next_sync_time - current_time
                    # Use async sleep for better performance
                    await asyncio.sleep(min(sleep_time, 0.05))
                    continue

                # We're at the exact boundary - start sync
                self.cycle_count += 1
                scheduled_time = next_sync_time  # Scheduled boundary time

                # Schedule next sync at exact boundary
                next_sync_time = next_sync_time + self.config.sync_interval

                # T026: Check if previous sync still running (but don't block)
                if self.syncing:
                    logging.warning(
                        f"Sync cycle {self.cycle_count}: Previous sync still in progress (running in background). "
                        f"Consider increasing sync_interval or timeout."
                    )
                    # Continue anyway - next cycle will start on schedule
                    continue

                # Mark sync as in progress
                self.syncing = True

                # Launch sync
                try:
                    # T024: Sync cycle logging with drift measurement
                    actual_start = time.time()
                    drift = (actual_start - scheduled_time) * 1000  # ms
                    if abs(drift) > 10:  # Log if drift > 10ms
                        logging.info(
                            f"Starting sync cycle {self.cycle_count} (drift: {drift:+.1f}ms)"
                        )
                    else:
                        logging.info(f"Starting sync cycle {self.cycle_count}")
                    start_time = actual_start

                    # Perform sync using persistent clients (NO asyncio.run() overhead!)
                    results = await sync_all_cameras_async(
                        self.config, self.async_clients
                    )

                    # Calculate duration
                    duration = time.time() - start_time

                    # Update statistics (always track, even if reporting is disabled)
                    self._update_statistics(
                        duration,
                        results["total_success"],
                        results["total_failed"],
                        results["cameras"],
                    )

                    # T024: Completion logging
                    time_to_next = next_sync_time - time.time()

                    if duration > self.config.sync_interval:
                        logging.warning(
                            f"Sync cycle {self.cycle_count} completed in {duration:.3f}s "
                            f"(exceeded interval of {self.config.sync_interval}s by {duration - self.config.sync_interval:.3f}s). "
                            f"Success: {results['total_success']}, Failed: {results['total_failed']}."
                        )
                    else:
                        logging.info(
                            f"Sync cycle {self.cycle_count} completed in {duration:.3f}s. "
                            f"Success: {results['total_success']}, Failed: {results['total_failed']}. "
                            f"Next cycle in {time_to_next:.3f}s."
                        )

                    # Check if it's time to print statistics (only if enabled)
                    if (
                        self.stats_interval is not None
                        and time.time() - self.last_stats_time >= self.stats_interval
                    ):
                        self._print_statistics()
                        self.last_stats_time = time.time()

                except Exception as e:
                    logging.error(f"Error during sync cycle {self.cycle_count}: {e}")

                finally:
                    self.syncing = False

        finally:
            # Cleanup: close all async clients
            logging.info("Closing async clients...")
            await self._close_async_clients()

            # Print final statistics summary (only if enabled)
            if self.stats_interval is not None and self.cycle_count > 0:
                logging.info("")
                logging.info("FINAL STATISTICS SUMMARY")
                self._print_statistics()

    def run(self):
        """
        Main sync loop - runs continuously until interrupted.
        """
        # T023: Setup signal handlers
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        self.running = True
        logging.info(f"Starting sync loop (interval: {self.config.sync_interval}s)")

        # Create and run persistent event loop (avoids asyncio.run() overhead)
        try:
            asyncio.run(self._run_async())
        except KeyboardInterrupt:
            logging.info("Received interrupt during async loop")
        finally:
            logging.info("Sync loop stopped. Goodbye!")


# ============================================================================
# Main Entry Point (T011-T017: CLI Implementation)
# ============================================================================

VERSION = "1.0.0"


def main():
    """Main entry point for CLI usage."""
    # T011: Implement main() with argparse
    parser = argparse.ArgumentParser(
        description="Hikvision Overlay Sync Manager - Automatically synchronize text overlays\n"
        "to Hikvision cameras at configurable intervals.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  overlay_sync_manager.py config.json           Start daemon with config
  overlay_sync_manager.py --validate config.json  Validate configuration
  overlay_sync_manager.py --once config.json     Run single sync cycle

Configuration:
  See config.example.json for configuration format and options.
  Configuration includes camera credentials, overlay definitions, and
  sync interval settings.

Signals:
  SIGINT/SIGTERM - Graceful shutdown after completing current sync

For more information, see README.md
        """,
    )

    # T012, T013: Add flags
    parser.add_argument(
        "-v",
        "--validate",
        action="store_true",
        help="Validate configuration and exit (don't start daemon)",
    )

    parser.add_argument(
        "-V", "--version", action="store_true", help="Show version and exit"
    )

    parser.add_argument(
        "-1",
        "--once",
        action="store_true",
        help="Run sync once and exit (no daemon mode)",
    )

    # Positional argument (optional when using --version)
    parser.add_argument(
        "config_file",
        metavar="CONFIG_FILE",
        type=str,
        nargs="?",
        help="Path to JSON configuration file",
    )

    args = parser.parse_args()

    # T013: Handle --version flag (no config needed)
    if args.version:
        print(f"Overlay Sync Manager v{VERSION}")
        print(f"Python {sys.version.split()[0]}")
        return 0

    # Config file is required for all other operations
    if not args.config_file:
        parser.error("CONFIG_FILE is required (unless using --version)")
        return 1

    # T015: Configuration error handling with descriptive messages
    config_path = Path(args.config_file)

    # Check if config file exists
    if not config_path.exists():
        print(f"✗ Configuration file not found: {config_path}", file=sys.stderr)
        print(
            "  Please create a configuration file or check the path.", file=sys.stderr
        )
        print(
            "  See config.example.json for an example configuration.", file=sys.stderr
        )
        return 1

    try:
        # Load configuration
        config = load_config(config_path)
    except json.JSONDecodeError as e:
        print("✗ Configuration file has invalid JSON syntax:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        print(f"  Line {e.lineno}, Column {e.colno}", file=sys.stderr)
        print(
            "  Use a JSON validator to check your configuration file.", file=sys.stderr
        )
        return 1
    except KeyError as e:
        print("✗ Configuration file is missing required field:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        print(
            "  See config.example.json for the complete configuration structure.",
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print("✗ Error loading configuration file:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        return 1

    # T016, T017: Validate configuration (validation already includes these checks)
    is_valid, errors = validate_config(config)

    # T012: Handle --validate flag
    if args.validate:
        print(f"Validating configuration file: {config_path}")
        if is_valid:
            print("✓ Configuration is valid")
            print(
                f"  - {len(config.cameras)} camera{'s' if len(config.cameras) != 1 else ''} configured"
            )
            total_overlays = sum(len(cam.overlays) for cam in config.cameras)
            print(
                f"  - {total_overlays} overlay{'s' if total_overlays != 1 else ''} total"
            )
            print(f"  - Sync interval: {config.sync_interval} seconds")
            return 0
        else:
            print("✗ Configuration is invalid:")
            for error in errors:
                print(f"  - {error}")
            return 1

    # For normal operation, fail if config is invalid
    if not is_valid:
        print("✗ Configuration is invalid:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "\nRun with --validate flag to see detailed validation results.",
            file=sys.stderr,
        )
        return 1

    # Setup logging
    setup_logging(config.log_level)
    logging.info(f"Starting Overlay Sync Manager v{VERSION}")
    logging.info(
        f"Loaded configuration: {len(config.cameras)} camera(s), "
        f"sync every {config.sync_interval}s"
    )

    # T038: Test camera connections before starting daemon
    # Skip connection test for --once mode (will be implemented later)
    if not args.once:
        reachable, total = test_all_cameras(config)

        if reachable == 0:
            logging.error(
                f"All {total} camera(s) are unreachable. "
                f"Check network connectivity, camera IP addresses, and credentials."
            )
            return 2  # Exit code 2 for connection failure
        elif reachable < total:
            logging.warning(
                f"Only {reachable}/{total} camera(s) are reachable. "
                f"Sync manager will start but some cameras may be offline."
            )
        else:
            logging.info(f"All {total} camera(s) are reachable.")

    # T042: Implement --once mode (run single sync cycle)
    if args.once:
        logging.info("One-shot mode: running single sync cycle")

        # Test camera connections
        reachable, total = test_all_cameras(config)

        if reachable == 0:
            logging.error(
                f"All {total} camera(s) are unreachable. "
                f"Check network connectivity, camera IP addresses, and credentials."
            )
            return 2  # Exit code 2 for connection failure

        # Run single sync cycle
        logging.info("Starting sync cycle")
        start_time = time.time()

        results = sync_all_cameras(config)

        duration = time.time() - start_time
        logging.info(
            f"Sync cycle completed in {duration:.1f}s. "
            f"Success: {results['total_success']}, Failed: {results['total_failed']}"
        )

        # Return 0 if all syncs succeeded, 1 if any failed
        return 0 if results["total_failed"] == 0 else 1

    # T027: Create SyncManager and run daemon mode
    manager = SyncManager(config)
    manager.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
