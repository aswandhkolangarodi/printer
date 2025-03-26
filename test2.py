from flask import Flask, jsonify
from escpos.printer import Usb
from escpos.exceptions import USBNotFoundError
import platform
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='printer_service.log'
)
logger = logging.getLogger(__name__)

# Printer configuration
PRINTER_VENDORS = [
    {'idVendor': 0x0483, 'idProduct': 0x5743},  # Bixolon
    {'idVendor': 0x04b8, 'idProduct': 0x0202},  # Epson
    {'idVendor': 0x067b, 'idProduct': 0x2305},  # Prolific
]

def detect_printer():
    """Try to detect connected USB printer"""
    for vendor in PRINTER_VENDORS:
        try:
            printer = Usb(vendor['idVendor'], vendor['idProduct'])
            logger.info(f"Found printer with vendor {vendor['idVendor']:04x}, product {vendor['idProduct']:04x}")
            return printer
        except USBNotFoundError:
            continue
    
    raise USBNotFoundError("No supported USB printer found")

@app.route('/print', methods=['GET'])
def test_print():
    """Endpoint to test if the printer is working"""
    try:
        printer = detect_printer()
        printer.text("Test Print Successful\n")
        printer.cut()
        printer.close()
        return jsonify({"success": True, "message": "Test print sent successfully"})
    except USBNotFoundError as e:
        logger.error(f"Printer detection failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 503
    except Exception as e:
        logger.error(f"Printing failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/status', methods=['GET'])
def service_status():
    """Endpoint to check service status"""
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
    logger.info("Starting printer service on port 5001")
    app.run(host='127.0.0.1', port=5001, debug=False)

if __name__ == '__main__':
    start_service()
