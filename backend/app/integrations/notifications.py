import httpx
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, List
from app.config import settings
from app.integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


class PushNotificationService(BaseIntegration):
    name = "fcm"
    requires_api_key = True
    api_key_setting = "FCM_SERVER_KEY"

    @staticmethod
    async def send_push(user_token: str, title: str, body: str, data: Optional[dict] = None) -> bool:
        if not settings.FCM_SERVER_KEY:
            logger.info(f"FCM not configured. Would send: {title} - {body}")
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "to": user_token,
                    "notification": {"title": title, "body": body, "sound": "default"},
                    "data": data or {},
                }
                response = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    headers={
                        "Authorization": f"key={settings.FCM_SERVER_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"FCM push failed: {e}")
            return False

    @staticmethod
    async def send_bulk(tokens: List[str], title: str, body: str, data: Optional[dict] = None) -> int:
        success = 0
        for token in tokens:
            if await PushNotificationService.send_push(token, title, body, data):
                success += 1
        return success


class EmailService(BaseIntegration):
    name = "email"
    requires_api_key = True
    api_key_setting = "EMAIL_API_KEY"

    @staticmethod
    async def send_email(to: str, subject: str, html_body: str, from_email: str = None) -> bool:
        sender = from_email or settings.SMTP_FROM_EMAIL
        if settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
            def _smtp_send():
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = sender
                msg["To"] = to
                msg["Reply-To"] = settings.SMTP_USER
                msg.attach(MIMEText(html_body, "html"))
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                    server.ehlo()
                    if settings.SMTP_PORT == 587:
                        server.starttls()
                        server.ehlo()
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.sendmail(sender, [to], msg.as_string())
            try:
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(loop.run_in_executor(None, _smtp_send), timeout=15)
                logger.info(f"Email sent to {to}: {subject}")
                return True
            except asyncio.TimeoutError:
                logger.error(f"SMTP email timed out sending to {to}")
                return False
            except Exception as e:
                logger.error(f"SMTP email failed: {e}")
                return False

        if settings.EMAIL_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        "https://api.emailjs.com/api/v1.0/email/send",
                        json={
                            "service_id": settings.EMAIL_API_KEY,
                            "template_id": "template_default",
                            "user_id": settings.EMAIL_API_KEY,
                            "template_params": {"to_email": to, "subject": subject, "message": html_body},
                        },
                    )
                    return response.status_code == 200
            except Exception as e:
                logger.error(f"EmailJS failed: {e}")

        logger.info(f"Email not configured. Would send to {to}: {subject}")
        return False

    @staticmethod
    async def send_support_email(ticket_id: str, name: str, farmer_id: str, category: str, subject: str, description: str, user_email: str = "") -> bool:
        to = settings.SUPPORT_EMAIL_TO
        html = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:650px;margin:auto;padding:20px;">
        <div style="background:linear-gradient(135deg,#2D8659,#1B5E3F);padding:24px;border-radius:12px 12px 0 0;text-align:center;">
            <h1 style="color:white;margin:0;font-size:22px;">Farm Assist Support Request</h1>
            <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">New ticket received</p>
        </div>
        <div style="background:#f8faf8;padding:24px;border:1px solid #e0e8e0;border-top:none;border-radius:0 0 12px 12px;">
            <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <tr><td style="padding:8px 0;color:#666;width:140px;">Ticket ID</td><td style="padding:8px 0;font-weight:700;color:#1B5E3F;">{ticket_id}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Category</td><td style="padding:8px 0;">{category}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Name</td><td style="padding:8px 0;">{name}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Farm ID</td><td style="padding:8px 0;">{farmer_id}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Email</td><td style="padding:8px 0;">{user_email or 'Not provided'}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Submitted</td><td style="padding:8px 0;">{datetime.utcnow().strftime('%d %b %Y, %I:%M %p UTC')}</td></tr>
            </table>
            <hr style="border:none;border-top:1px solid #e0e8e0;margin:16px 0;">
            <h3 style="font-size:15px;color:#1B5E3F;margin-bottom:8px;">Subject</h3>
            <p style="font-size:14px;color:#333;margin:0 0 16px;">{subject}</p>
            <h3 style="font-size:15px;color:#1B5E3F;margin-bottom:8px;">Description</h3>
            <div style="background:white;padding:16px;border-radius:8px;border:1px solid #e0e8e0;font-size:13px;color:#444;line-height:1.7;white-space:pre-wrap;">{description}</div>
        </div>
        <p style="text-align:center;color:#999;font-size:11px;margin-top:16px;">Farm Assist - Agriculture Super App | Automated Notification</p>
        </body></html>"""
        return await EmailService.send_email(to, f"Farm Assist Support Request - {category}", html)

    @staticmethod
    async def send_feedback_email(feedback_id: str, name: str, farmer_id: str, feedback_type: str, rating: int, message: str, related_page: str = "", user_email: str = "") -> bool:
        to = settings.SUPPORT_EMAIL_TO
        stars = "&#9733;" * rating + "&#9734;" * (5 - rating)
        html = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:650px;margin:auto;padding:20px;">
        <div style="background:linear-gradient(135deg,#2D8659,#1B5E3F);padding:24px;border-radius:12px 12px 0 0;text-align:center;">
            <h1 style="color:white;margin:0;font-size:22px;">Farm Assist Feedback</h1>
            <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">New feedback received</p>
        </div>
        <div style="background:#f8faf8;padding:24px;border:1px solid #e0e8e0;border-top:none;border-radius:0 0 12px 12px;">
            <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <tr><td style="padding:8px 0;color:#666;width:140px;">Feedback ID</td><td style="padding:8px 0;font-weight:700;color:#1B5E3F;">{feedback_id}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Type</td><td style="padding:8px 0;">{feedback_type}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Rating</td><td style="padding:8px 0;font-size:18px;color:#F5A623;">{stars} ({rating}/5)</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Name</td><td style="padding:8px 0;">{name}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Farm ID</td><td style="padding:8px 0;">{farmer_id}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Email</td><td style="padding:8px 0;">{user_email or 'Not provided'}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Page/Feature</td><td style="padding:8px 0;">{related_page or 'General'}</td></tr>
                <tr><td style="padding:8px 0;color:#666;">Submitted</td><td style="padding:8px 0;">{datetime.utcnow().strftime('%d %b %Y, %I:%M %p UTC')}</td></tr>
            </table>
            <hr style="border:none;border-top:1px solid #e0e8e0;margin:16px 0;">
            <h3 style="font-size:15px;color:#1B5E3F;margin-bottom:8px;">Message</h3>
            <div style="background:white;padding:16px;border-radius:8px;border:1px solid #e0e8e0;font-size:13px;color:#444;line-height:1.7;white-space:pre-wrap;">{message}</div>
        </div>
        <p style="text-align:center;color:#999;font-size:11px;margin-top:16px;">Farm Assist - Agriculture Super App | Automated Notification</p>
        </body></html>"""
        return await EmailService.send_email(to, f"Farm Assist Feedback - {feedback_type}", html)

    @staticmethod
    async def send_otp_email(to: str, otp: str) -> bool:
        html = f"""
        <html><body style="font-family: Arial; max-width: 600px; margin: auto;">
        <h2 style="color: #2D8659;">Farm Assist - OTP Verification</h2>
        <p>Your OTP for verification is:</p>
        <h1 style="color: #1B5E3F; font-size: 36px; letter-spacing: 5px;">{otp}</h1>
        <p>This OTP is valid for 10 minutes.</p>
        <hr><p style="color: #888; font-size: 12px;">Farm Assist - Agriculture Super App</p>
        </body></html>"""
        return await EmailService.send_email(to, "Farm Assist - OTP Verification", html)


class SMSService(BaseIntegration):
    name = "sms"
    requires_api_key = True
    api_key_setting = "SMS_API_KEY"

    @staticmethod
    async def send_sms(phone: str, message: str) -> bool:
        if not settings.SMS_API_KEY:
            logger.info(f"SMS not configured. Would send to {phone}: {message}")
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.msg91.com/api/v5/flow/",
                    json={
                        "sender": settings.SMS_SENDER_ID or "FARMAS",
                        "mobiles": phone,
                        "message": message,
                    },
                    headers={"authkey": settings.SMS_API_KEY},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"SMS API failed: {e}")
            return False

    @staticmethod
    async def send_otp_sms(phone: str, otp: str) -> bool:
        return await SMSService.send_sms(phone, f"Your Farm Assist OTP is {otp}. Valid for 10 minutes.")


class QRCodeService(BaseIntegration):
    name = "qrcode"
    requires_api_key = False

    @staticmethod
    def generate_qr(data: str, size: int = 200) -> dict:
        try:
            import qrcode
            from io import BytesIO
            import base64
            qr = qrcode.QRCode(box_size=10, border=2)
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            return {"qr_data": f"data:image/png;base64,{img_base64}", "format": "png", "size": size}
        except ImportError:
            return {"qr_data": None, "format": "none", "note": "qrcode library not installed"}
