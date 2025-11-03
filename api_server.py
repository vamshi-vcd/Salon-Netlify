"""
FastAPI Backend for Agentic Salon AI Voice Assistant
Handles QR code scanning, voice calls, and webhook endpoints
"""

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from typing import Optional, Dict, Any
import os
from datetime import datetime

# Import our AI system
from voice_agent import AgenticSalonAI, TWILIO_AVAILABLE, WEBHOOK_URL
try:
    from config import config
    WEBHOOK_URL = config.WEBHOOK_URL
except ImportError:
    pass
# Optional Vonage support (no webhooks needed if using answer_url hosted by provider)
try:
    import vonage  # type: ignore
    VONAGE_AVAILABLE = True
except Exception:
    vonage = None  # type: ignore
    VONAGE_AVAILABLE = False

VONAGE_API_KEY = os.getenv("VONAGE_API_KEY", getattr(config, "VONAGE_API_KEY", "")) if 'config' in globals() else os.getenv("VONAGE_API_KEY", "")
VONAGE_API_SECRET = os.getenv("VONAGE_API_SECRET", getattr(config, "VONAGE_API_SECRET", "")) if 'config' in globals() else os.getenv("VONAGE_API_SECRET", "")
VONAGE_PHONE_NUMBER = os.getenv("VONAGE_PHONE_NUMBER", getattr(config, "VONAGE_PHONE_NUMBER", "")) if 'config' in globals() else os.getenv("VONAGE_PHONE_NUMBER", "")
# AI Studio or hosted NCCO URL that controls the call (no repo webhook required)
VONAGE_ANSWER_URL = os.getenv("VONAGE_ANSWER_URL", getattr(config, "VONAGE_ANSWER_URL", "")) if 'config' in globals() else os.getenv("VONAGE_ANSWER_URL", "")

def get_vonage_client():
    if not VONAGE_AVAILABLE:
        return None
    if not (VONAGE_API_KEY and VONAGE_API_SECRET):
        return None
    try:
        client = vonage.Client(key=VONAGE_API_KEY, secret=VONAGE_API_SECRET)
        return client
    except Exception:
        return None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Salon AI Voice Assistant API",
    description="Agentic AI system for salon voice calls and bookings",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AI system
salon_ai = AgenticSalonAI()

# Store active sessions
active_sessions: Dict[str, AgenticSalonAI] = {}

@app.get("/", response_class=HTMLResponse)
async def home():
    """Home page with QR code scanning interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Goodness Glamour Salon - AI Voice Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                text-align: center;
            }
            h1 {
                color: #fff;
                margin-bottom: 10px;
            }
            .subtitle {
                color: #f0f0f0;
                margin-bottom: 30px;
            }
            .qr-section {
                background: rgba(255, 255, 255, 0.2);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }
            .phone-input {
                width: 100%;
                padding: 15px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                margin: 10px 0;
                box-sizing: border-box;
            }
            .call-button {
                background: #4CAF50;
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                cursor: pointer;
                margin: 10px;
                transition: background 0.3s;
            }
            .call-button:hover {
                background: #45a049;
            }
            .info-section {
                background: rgba(255, 255, 255, 0.1);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
                text-align: left;
            }
            .service-list {
                list-style: none;
                padding: 0;
            }
            .service-list li {
                padding: 5px 0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✨ Goodness Glamour Salon</h1>
            <p class="subtitle">AI-Powered Voice Assistant</p>
            
            <div class="qr-section">
                <h3>📱 Get Instant AI Call</h3>
                <p>Enter your phone number to receive an instant call from our AI assistant</p>
                <form id="phoneForm">
                    <input type="tel" id="phone" class="phone-input" placeholder="Enter your phone number (e.g., +919876543210)" required>
                    <br>
                    <button type="submit" class="call-button">📞 Get AI Call Now</button>
                </form>
                <div id="status"></div>
            </div>
            
            <div class="info-section">
                <h3>🎯 Our Services</h3>
                <ul class="service-list">
                    <li>💇‍♀️ Haircut & Styling (₹500-₹1,500)</li>
                    <li>🎨 Hair Coloring (₹2,000-₹5,000)</li>
                    <li>🧖‍♀️ Hair Spa Treatment (₹1,500-₹3,000)</li>
                    <li>💆‍♀️ Keratin Treatment (₹4,000-₹8,000)</li>
                    <li>👶 Kids Haircut (₹300-₹700)</li>
                    <li>🎉 Party Hairstyle (₹800-₹1,500)</li>
                    <li>💄 Bridal Hair & Makeup (₹15,000-₹30,000)</li>
                </ul>
                <p><strong>🏠 Doorstep Service Available</strong><br>
                📞 Contact: 9036626642<br>
                ⏰ Hours: Mon-Sun, 9 AM - 8 PM</p>
            </div>
        </div>
        
        <script>
            document.getElementById('phoneForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                const phone = document.getElementById('phone').value;
                const status = document.getElementById('status');
                
                if (!phone) {
                    status.innerHTML = '<p style="color: #ffeb3b;">Please enter a phone number</p>';
                    return;
                }
                
                status.innerHTML = '<p style="color: #4CAF50;">🔄 Initiating AI call...</p>';
                
                try {
                    const response = await fetch('/trigger-call', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({phone: phone})
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        status.innerHTML = '<p style="color: #4CAF50;">✅ AI call initiated! You should receive a call shortly.</p>';
                    } else {
                        status.innerHTML = '<p style="color: #f44336;">❌ ' + result.message + '</p>';
                    }
                } catch (error) {
                    status.innerHTML = '<p style="color: #f44336;">❌ Error: ' + error.message + '</p>';
                }
            });
        </script>
    </body>
    </html>
    """

@app.post("/trigger-call")
async def trigger_call(request: Dict[str, str]):
    """Trigger a voice call to customer"""
    try:
        phone = request.get("phone")
        if not phone:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        # Clean phone number
        phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone.startswith("+"):
            phone = "+91" + phone.lstrip("0")
        
        # Prefer Vonage if configured with hosted answer_url (no repo webhook needed)
        vonage_client = get_vonage_client()
        if vonage_client and VONAGE_PHONE_NUMBER and VONAGE_ANSWER_URL:
            try:
                response = vonage_client.voice.create_call({
                    'to': [{'type': 'phone', 'number': phone}],
                    'from': {'type': 'phone', 'number': VONAGE_PHONE_NUMBER},
                    'answer_url': [VONAGE_ANSWER_URL]
                })
                call_id = response.get('uuid') if isinstance(response, dict) else None
                return {"success": True, "provider": "vonage", "message": f"AI call initiated to {phone}", "call_id": call_id}
            except Exception as e:
                logger.error(f"Vonage call failed, falling back to Twilio: {e}")
                # Fall through to Twilio below
        
        # Twilio fallback using our existing handler (requires WEBHOOK_URL and webhook route)
        webhook_url = f"{WEBHOOK_URL}/voice/webhook"
        success = salon_ai.trigger_voice_call(phone, webhook_url)
        if success:
            return {"success": True, "provider": "twilio", "message": f"AI call initiated to {phone}"}
        else:
            return {"success": False, "message": "Failed to initiate call. Configure Vonage (VONAGE_API_KEY/SECRET/PHONE/ANSWER_URL) or Twilio (SID/TOKEN/PHONE/WEBHOOK_URL)."}
    
    except Exception as e:
        logger.error(f"Error triggering call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/voice/webhook")
async def voice_webhook(request: Request):
    """Handle incoming voice call webhook from Twilio"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        speech_result = form_data.get("SpeechResult", "")
        
        logger.info(f"Voice webhook received - CallSid: {call_sid}, Speech: {speech_result}")
        
        if not speech_result:
            # Initial call - greet the customer
            greeting = "Hello! Welcome to Goodness Glamour Salon. I'm your AI assistant. How can I help you today?"
            twiml_response = salon_ai.twilio_handler.generate_twiml_response(greeting)
        else:
            # Process the speech input
            twiml_response = salon_ai.process_voice_call(speech_result)
        
        return Response(content=twiml_response, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error processing voice webhook: {e}")
        error_response = salon_ai.twilio_handler.generate_twiml_response(
            "I'm sorry, I'm having trouble. Please try again later."
        )
        return Response(content=error_response, media_type="application/xml")

@app.get("/voice/process")
async def voice_process(request: Request):
    """Handle voice call processing"""
    try:
        speech_result = request.query_params.get("SpeechResult", "")
        
        if not speech_result:
            greeting = "Hello! Welcome to Goodness Glamour Salon. How can I help you today?"
            return Response(content=salon_ai.twilio_handler.generate_twiml_response(greeting), media_type="application/xml")
        
        # Process the speech input
        twiml_response = salon_ai.process_voice_call(speech_result)
        return Response(content=twiml_response, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error processing voice: {e}")
        error_response = salon_ai.twilio_handler.generate_twiml_response(
            "I'm sorry, I'm having trouble. Please try again."
        )
        return Response(content=error_response, media_type="application/xml")

@app.get("/bookings")
async def get_bookings():
    """Get all bookings"""
    try:
        # This would typically query your database
        # For now, return a sample response
        return {
            "bookings": [],
            "message": "Bookings endpoint - implement database query here"
        }
    except Exception as e:
        logger.error(f"Error getting bookings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/bookings")
async def create_booking(booking_data: Dict[str, Any]):
    """Create a new booking"""
    try:
        # Process booking through AI system
        response = salon_ai.process_user_input(f"Book appointment: {booking_data}")
        return {"success": True, "message": response}
    except Exception as e:
        logger.error(f"Error creating booking: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "twilio_available": TWILIO_AVAILABLE,
        "ai_system": "operational"
    }

@app.get("/test-ai")
async def test_ai():
    """Test AI system with sample query"""
    try:
        test_query = "What services do you offer?"
        response = salon_ai.process_user_input(test_query)
        return {
            "query": test_query,
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error testing AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
