from flask import Flask, request, jsonify
from escpos.printer import Usb
from escpos.exceptions import USBNotFoundError
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from PIL import Image
import qrcode
import platform
import os
import logging
from datetime import datetime
import atexit
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='printer_service.log'
)
logger = logging.getLogger(__name__)

# Configuration - Now using environment variables
CONFIG = {
    'port': int(os.getenv('PRINTER_PORT', 5001)),
    'auth_token': os.getenv('AUTH_TOKEN', 'your-secret-token-here'),
    'printer_vendors': [
        {'idVendor': 0x0483, 'idProduct': 0x5743},  # Bixolon
        {'idVendor': 0x04b8, 'idProduct': 0x0202},  # Epson
        {'idVendor': 0x067b, 'idProduct': 0x2305},  # Prolific
    ],
    'default_company': {
        'name': "STAGMENFASHION",
        'phones': ["+917736444674", "+918943888200"],
        'address': "Kondotty",
        'gstin': "32MMRPS3804DIZS",
        'website': "https://stagmenfashion.com"
    }
}

def validate_token():
    """Validate authentication token"""
    auth_header = request.headers.get('Authorization')
    expected_token = f"Bearer {CONFIG['auth_token']}"
    
    # Debug logging
    logger.debug(f"Expected token: {expected_token}")
    logger.debug(f"Received token: {auth_header}")
    
    if not auth_header or auth_header != expected_token:
        logger.warning(f"Unauthorized access attempt. Expected: {expected_token}, Got: {auth_header}")
        return False
    return True

def detect_printer():
    """Try to detect connected USB printer"""
    for vendor in CONFIG['printer_vendors']:
        try:
            printer = Usb(vendor['idVendor'], vendor['idProduct'])
            logger.info(f"Found printer with vendor {vendor['idVendor']:04x}, product {vendor['idProduct']:04x}")
            return printer
        except USBNotFoundError:
            continue
    
    raise USBNotFoundError("No supported USB printer found")

def generate_barcode(invoice_number):
    """Generate barcode image for invoice number"""
    code = barcode.get('code128', invoice_number, writer=ImageWriter())
    buffer = BytesIO()
    code.write(buffer)
    buffer.seek(0)
    return Image.open(buffer)

def generate_qr_code(url):
    """Generate QR code image for website URL"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return Image.open(buffer)

def print_invoice(data):
    """Print invoice with barcode and QR code"""
    try:
        printer = detect_printer()
    except USBNotFoundError as e:
        logger.error(f"Printer detection failed: {str(e)}")
        return False, str(e)
    
    try:
        # Print header (centered and bold)
        printer.set(align='center', bold=True)
        printer.text(f"{data.get('company_name', CONFIG['default_company']['name'])}\n")
        printer.set(bold=False)
        
        # Print contact information
        for number in data.get('phone_numbers', CONFIG['default_company']['phones']):
            printer.text(f"{number}\n")
        
        # Print address and GSTIN
        printer.text(f"{data.get('address', CONFIG['default_company']['address'])}\n")
        printer.text(f"GSTIN: {data.get('gstin', CONFIG['default_company']['gstin'])}\n")
        
        # Divider line
        printer.text("-" * 32 + "\n")
        
        # Print invoice info
        printer.set(align='left')
        printer.text(f"Invoice #: {data['invoice_number']}\n")
        printer.text(f"Date: {data['invoice_date']}\n")
        if data.get('invoice_time'):
            printer.text(f"Time: {data['invoice_time']}\n")
        printer.text(f"Customer: {data['customer_name']}\n")
        
        # Divider line
        printer.text("-" * 32 + "\n")
        
        # Print items table header
        printer.text(f"{'Item':<20}{'Qty':>4}{'Price':>8}{'Total':>8}\n")
        
        # Print items
        for item in data['items']:
            name_parts = [item['name'][i:i+20] for i in range(0, len(item['name']), 20)]
            for i, part in enumerate(name_parts):
                if i == 0:
                    printer.text(f"{part:<20}{item['quantity']:>4.2f}{item['price']:>8.2f}{item['quantity'] * item['price']:>8.2f}\n")
                else:
                    printer.text(f"{part:<20}\n")
        
        # Divider line
        printer.text("-" * 32 + "\n")
        
        # Print totals
        printer.text(f"{'Subtotal:':<20}{data['subtotal']:>12.2f}\n")
        printer.text(f"{'Discount:':<20}{data.get('discount', 0.00):>12.2f}\n")
        printer.set(bold=True)
        printer.text(f"{'GRAND TOTAL:':<20}{data['total']:>12.2f}\n")
        printer.set(bold=False)
        
        # Divider line
        printer.text("-" * 32 + "\n")
        
        # Print terms and conditions
        terms = [
            "* NO REFUND.",
            "* Returns accepted within 7 days with receipt.",
            "* No Product Will Be Replaced Without Bill.",
            "* Please Check Your Bill Before Leaving The Shop."
        ]
        for term in terms:
            printer.text(f"{term}\n")
        
        # Divider line
        printer.text("-" * 32 + "\n")
        
        # Print invoice number again
        printer.set(align='center')
        printer.text(f"{data['invoice_number']}\n")
        
        # Divider line
        printer.text("-" * 32 + "\n")
        
        # Generate and print barcode
        barcode_img = generate_barcode(data['invoice_number'])
        printer.image(barcode_img, impl="bitImageColumn")
        printer.text("\n")
        
        # Generate and print QR code
        qr_img = generate_qr_code(data.get('website_url', CONFIG['default_company']['website']))
        printer.image(qr_img, impl="bitImageColumn")
        printer.text("\n")
        
        # Print footer message
        printer.set(align='center')
        printer.text("ENJOY FROM EVERYWHERE\n")
        printer.text("THANK YOU FOR WATCHING!\n")
        
        # Cut paper (if supported)
        printer.cut()
        
        return True, "Invoice printed successfully"
    except Exception as e:
        logger.error(f"Printing failed: {str(e)}")
        return False, str(e)
    finally:
        printer.close()

@app.route('/print', methods=['POST'])
def handle_print():
    """Endpoint to handle print requests"""
    if not validate_token():
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    if not request.is_json:
        return jsonify({"success": False, "message": "Request must be JSON"}), 400
    
    data = request.get_json()
    required_fields = [
        'invoice_number', 'invoice_date', 'customer_name',
        'items', 'subtotal', 'total'
    ]
    
    for field in required_fields:
        if field not in data:
            return jsonify({"success": False, "message": f"Missing required field: {field}"}), 400
    
    success, message = print_invoice(data)
    status_code = 200 if success else 500
    return jsonify({"success": success, "message": message}), status_code

@app.route('/status', methods=['GET'])
def service_status():
    """Endpoint to check service status"""
    if not validate_token():
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    try:
        printer = detect_printer()
        printer.close()
        return jsonify({
            "success": True,
            "message": "Printer service is running",
            "system": platform.system(),
            "printer": "Connected"
        })
    except USBNotFoundError as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "system": platform.system(),
            "printer": "Not connected"
        }), 503

def start_service():
    """Start the Flask service"""
    logger.info(f"Starting printer service on port {CONFIG['port']}")
    logger.info(f"Using auth token: {CONFIG['auth_token']}")
    app.run(host='127.0.0.1', port=CONFIG['port'], debug=False)

if __name__ == '__main__':
    start_service()