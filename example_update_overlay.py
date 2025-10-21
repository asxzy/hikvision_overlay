#!/usr/bin/env python3
"""
Simple script to update Hikvision camera text overlay.

Based on the logic from scrypted-hikvision-utilities plugin.
Uses HTTP Digest authentication to communicate with Hikvision ISAPI.
"""

import argparse
import sys
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
from typing import Optional
import urllib3


class HikvisionOverlay:
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
        if ':' not in self.ip:
            self.ip = f"{self.ip}:80"

    def get_overlay_text(self, overlay_id: str) -> Optional[ET.Element]:
        """
        Get current text overlay configuration.

        Args:
            overlay_id: Overlay ID (e.g., "1", "2", etc.)

        Returns:
            XML Element tree of the overlay, or None on error
        """
        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays/text/{overlay_id}"

        try:
            response = requests.get(
                url,
                auth=self.auth,
                verify=False,
                headers={'Content-Type': 'application/xml'},
                timeout=10
            )
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)
            return root

        except requests.exceptions.RequestException as e:
            print(f"Error getting overlay: {e}", file=sys.stderr)
            return None

    def get_screen_size(self) -> tuple[int, int]:
        """
        Get normalized screen size from camera.

        Returns:
            Tuple of (width, height), or (704, 576) as default
        """
        if self.screen_width is not None and self.screen_height is not None:
            return self.screen_width, self.screen_height

        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays"

        try:
            response = requests.get(
                url,
                auth=self.auth,
                verify=False,
                headers={'Content-Type': 'application/xml'},
                timeout=10
            )
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)
            ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

            # Find normalizedScreenSize
            width_elem = root.find('.//ns:normalizedScreenWidth' if ns else './/normalizedScreenWidth', ns)
            height_elem = root.find('.//ns:normalizedScreenHeight' if ns else './/normalizedScreenHeight', ns)

            if width_elem is not None and height_elem is not None:
                self.screen_width = int(width_elem.text)
                self.screen_height = int(height_elem.text)
            else:
                # Default values
                self.screen_width = 704
                self.screen_height = 576

            return self.screen_width, self.screen_height

        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"Error getting screen size: {e}, using defaults", file=sys.stderr)
            self.screen_width = 704
            self.screen_height = 576
            return self.screen_width, self.screen_height

    def update_overlay_text(self, overlay_id: str, new_text: str, enable: bool = True,
                           position_x: int = None, position_y: int = None,
                           position_x_percent: float = None, position_y_percent: float = None,
                           verbose: bool = False) -> bool:
        """
        Update text overlay with new text.

        Args:
            overlay_id: Overlay ID (e.g., "1", "2", etc.)
            new_text: New text to display
            enable: Enable the overlay if True
            position_x: X position in pixels (None to keep current)
            position_y: Y position in pixels (None to keep current)
            position_x_percent: X position as percentage 0-100 (overrides position_x)
            position_y_percent: Y position as percentage 0-100 (overrides position_y)

        Returns:
            True on success, False on error
        """
        # Get screen size for percentage calculations
        if position_x_percent is not None or position_y_percent is not None:
            screen_width, screen_height = self.get_screen_size()

            if verbose:
                print(f"Screen size: {screen_width}x{screen_height}", file=sys.stderr)

            if position_x_percent is not None:
                position_x = int(screen_width * position_x_percent / 100)
                if verbose:
                    print(f"X: {position_x_percent}% = {position_x} pixels", file=sys.stderr)

            if position_y_percent is not None:
                position_y = int(screen_height * position_y_percent / 100)
                if verbose:
                    print(f"Y: {position_y_percent}% = {position_y} pixels", file=sys.stderr)

        # First, get current overlay configuration
        overlay_xml = self.get_overlay_text(overlay_id)
        if overlay_xml is None:
            return False

        # Extract namespace if present
        ns = {'ns': overlay_xml.tag.split('}')[0].strip('{')} if '}' in overlay_xml.tag else {}

        # Register namespace to avoid ns0: prefix
        if ns:
            ET.register_namespace('', ns['ns'])

        # Update the displayText field
        display_text_elem = overlay_xml.find('ns:displayText' if ns else 'displayText', ns)
        if display_text_elem is not None:
            display_text_elem.text = new_text
        else:
            print(f"Error: displayText element not found in overlay {overlay_id}", file=sys.stderr)
            return False

        # Enable overlay if requested
        if enable:
            enabled_elem = overlay_xml.find('ns:enabled' if ns else 'enabled', ns)
            if enabled_elem is not None:
                enabled_elem.text = 'true'

        # Update position if provided
        if position_x is not None:
            pos_x_elem = overlay_xml.find('ns:positionX' if ns else 'positionX', ns)
            if pos_x_elem is not None:
                pos_x_elem.text = str(position_x)

        if position_y is not None:
            pos_y_elem = overlay_xml.find('ns:positionY' if ns else 'positionY', ns)
            if pos_y_elem is not None:
                pos_y_elem.text = str(position_y)

        # Convert back to XML string
        xml_str = ET.tostring(overlay_xml, encoding='unicode', method='xml')

        if verbose:
            print(f"Sending XML:\n{xml_str}", file=sys.stderr)

        # Send PUT request to update overlay
        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays/text/{overlay_id}"

        try:
            response = requests.put(
                url,
                auth=self.auth,
                verify=False,
                headers={'Content-Type': 'application/xml'},
                data=xml_str,
                timeout=10
            )
            response.raise_for_status()

            print(f"Successfully updated overlay {overlay_id} with text: {new_text}")
            return True

        except requests.exceptions.RequestException as e:
            print(f"Error updating overlay: {e}", file=sys.stderr)
            return False

    def list_overlays(self, verbose: bool = False) -> Optional[list]:
        """
        List all available text overlays.

        Args:
            verbose: Print detailed debug information

        Returns:
            List of overlay IDs, or None on error
        """
        url = f"http://{self.ip}/ISAPI/System/Video/inputs/channels/{self.channel}/overlays"

        try:
            if verbose:
                print(f"Requesting: {url}", file=sys.stderr)

            response = requests.get(
                url,
                auth=self.auth,
                verify=False,
                headers={'Content-Type': 'application/xml'},
                timeout=10
            )

            if verbose:
                print(f"Response status: {response.status_code}", file=sys.stderr)
                print(f"Response body:\n{response.text[:500]}", file=sys.stderr)

            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.text)

            # Extract namespace if present
            ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

            # Find all TextOverlay elements
            overlay_ids = []
            search_path = './/ns:TextOverlay' if ns else './/TextOverlay'
            for text_overlay in root.findall(search_path, ns):
                overlay_id = text_overlay.find('ns:id' if ns else 'id', ns)
                if overlay_id is not None and overlay_id.text:
                    overlay_ids.append(overlay_id.text)

            # If no overlays found in the list, check the size attribute and probe for IDs
            if not overlay_ids:
                text_overlay_list = root.find('.//ns:TextOverlayList' if ns else './/TextOverlayList', ns)
                if verbose:
                    print(f"TextOverlayList element: {text_overlay_list}", file=sys.stderr)

                if text_overlay_list is not None:
                    size = text_overlay_list.get('size')
                    if verbose:
                        print(f"Size attribute: {size}", file=sys.stderr)

                    if size and int(size) > 0:
                        if verbose:
                            print(f"TextOverlayList has size={size} but no child elements. Probing for overlay IDs...", file=sys.stderr)

                        # Try probing IDs 1 through size
                        for i in range(1, int(size) + 1):
                            overlay_id = str(i)
                            if verbose:
                                print(f"Probing overlay ID: {overlay_id}", file=sys.stderr)
                            test_overlay = self.get_overlay_text(overlay_id)
                            if test_overlay is not None:
                                overlay_ids.append(overlay_id)
                                if verbose:
                                    print(f"Found overlay ID: {overlay_id}", file=sys.stderr)
                            else:
                                if verbose:
                                    print(f"Overlay ID {overlay_id} not found", file=sys.stderr)

            if verbose:
                print(f"Found overlay IDs: {overlay_ids}", file=sys.stderr)

            return overlay_ids if overlay_ids else None

        except requests.exceptions.RequestException as e:
            print(f"Error listing overlays: {e}", file=sys.stderr)
            if verbose and hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}", file=sys.stderr)
                print(f"Response body: {e.response.text[:500]}", file=sys.stderr)
            return None


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description='Update Hikvision camera text overlays via ISAPI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s 192.168.1.100 admin password123 --list
  %(prog)s 192.168.1.100 admin password123 --overlay 1 --text "Hello World"
  %(prog)s 192.168.1.100:8080 admin password123 --overlay 2 --text "Temperature: 25C" --channel 2
        '''
    )

    # Required arguments
    parser.add_argument('ip', help='Camera IP address (with optional port, e.g., 192.168.1.100 or 192.168.1.100:80)')
    parser.add_argument('username', help='Camera username')
    parser.add_argument('password', help='Camera password')

    # Optional arguments
    parser.add_argument('-c', '--channel', type=int, default=1,
                        help='Video channel number (default: 1)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose debug output')

    # Action group - mutually exclusive
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument('-l', '--list', action='store_true',
                              help='List all available text overlay IDs')
    action_group.add_argument('-o', '--overlay', type=str, metavar='ID',
                              help='Overlay ID to update')

    # Text argument (required when using --overlay)
    parser.add_argument('-t', '--text', type=str,
                        help='New text to display (required with --overlay)')
    parser.add_argument('--no-enable', action='store_true',
                        help='Do not enable the overlay when updating (default: enable)')
    parser.add_argument('-x', '--position-x', type=int, metavar='X',
                        help='X position in pixels (default: keep current)')
    parser.add_argument('-y', '--position-y', type=int, metavar='Y',
                        help='Y position in pixels (default: keep current)')
    parser.add_argument('--position-x-percent', type=float, metavar='%',
                        help='X position as percentage 0-100 (overrides -x)')
    parser.add_argument('--position-y-percent', type=float, metavar='%',
                        help='Y position as percentage 0-100 (overrides -y)')

    args = parser.parse_args()

    # Validate that --text is provided when --overlay is used
    if args.overlay and not args.text:
        parser.error('--text is required when --overlay is specified')

    # Disable SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Create client
    client = HikvisionOverlay(args.ip, args.username, args.password, args.channel)

    # Execute action
    if args.list:
        if args.verbose:
            print(f"Listing overlays for {args.ip}...")
        overlay_ids = client.list_overlays(verbose=args.verbose)
        if overlay_ids:
            print(f"Available overlay IDs: {', '.join(overlay_ids)}")
            return 0
        else:
            print("No overlays found or error occurred")
            return 1
    else:
        # Update overlay
        success = client.update_overlay_text(
            args.overlay,
            args.text,
            enable=not args.no_enable,
            position_x=args.position_x,
            position_y=args.position_y,
            position_x_percent=args.position_x_percent,
            position_y_percent=args.position_y_percent,
            verbose=args.verbose
        )
        return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
