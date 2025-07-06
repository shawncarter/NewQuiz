import socket
import qrcode
import io
import base64
from django.conf import settings


def get_server_ip():
    """Get the current server's IP address"""
    try:
        # Create a socket connection to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a remote address (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Fallback to localhost if unable to determine IP
        return "127.0.0.1"


def generate_qr_code(game_code):
    """Generate a QR code for the game join URL with current IP address"""
    # Get the current server IP
    server_ip = get_server_ip()
    
    # Determine the port (default to 8000 for development)
    try:
        port = getattr(settings, 'QR_CODE_PORT', 8000)
    except:
        port = 8000
    
    # Create the join URL with IP address
    join_url = f"http://{server_ip}:{port}/join/?code={game_code}"
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(join_url)
    qr.make(fit=True)
    
    # Create QR code image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for embedding in HTML
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return {
        'qr_code_base64': img_base64,
        'join_url': join_url,
        'server_ip': server_ip
    }