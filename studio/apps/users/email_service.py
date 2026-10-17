import os
import logging
import requests

logger = logging.getLogger(__name__)

BREVO_SMTP_URL = "https://api.brevo.com/v3/smtp/email"


def _brevo_headers():
    return {
        "api-key": os.getenv("BREVO_API_KEY", ""),
        "Content-Type": "application/json",
    }


def _sender():
    return {
        "name": os.getenv("BREVO_SENDER_NAME", "Aura Estudio Pilates"),
        "email": os.getenv("BREVO_SENDER_EMAIL", "noreply@auraestudio.com"),
    }


def send_verification_email(email: str, name: str, token: str) -> None:
    """
    Envía el email de verificación de cuenta al alumno recién registrado.
    El frontend usa el token para llamar a /register/verify-email/.
    """
    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    verify_link = f"{frontend_url}/verify-email?token={token}" if frontend_url else token

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #333;">Hola {name}, verificá tu cuenta</h2>
      <p>Gracias por registrarte en <strong>Aura Estudio Pilates</strong>.</p>
      <p>Hacé clic en el botón para activar tu cuenta (válido por 24 horas):</p>
      <p style="text-align: center; margin: 32px 0;">
        <a href="{verify_link}"
           style="background-color: #c8a2c8; color: white; padding: 14px 28px;
                  text-decoration: none; border-radius: 6px; font-size: 16px;">
          Verificar cuenta
        </a>
      </p>
      <p style="color: #888; font-size: 13px;">
        Si no te registraste vos, ignorá este mensaje.
      </p>
    </div>
    """

    payload = {
        "sender": _sender(),
        "to": [{"email": email, "name": name}],
        "subject": "Verificá tu cuenta — Aura Estudio Pilates",
        "htmlContent": html,
    }

    _send(payload, context="verification")


def send_password_reset_email(email: str, name: str, token: str) -> None:
    """
    Envía el email de recuperación de contraseña.
    El frontend usa el token para llamar a /password-reset/confirm/.
    """
    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    reset_link = f"{frontend_url}/reset-password?token={token}" if frontend_url else token

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #333;">Hola {name}, recuperá tu contraseña</h2>
      <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta en
         <strong>Aura Estudio Pilates</strong>.</p>
      <p>Hacé clic en el botón para crear una nueva contraseña (válido por 1 hora):</p>
      <p style="text-align: center; margin: 32px 0;">
        <a href="{reset_link}"
           style="background-color: #c8a2c8; color: white; padding: 14px 28px;
                  text-decoration: none; border-radius: 6px; font-size: 16px;">
          Restablecer contraseña
        </a>
      </p>
      <p style="color: #888; font-size: 13px;">
        Si no solicitaste este cambio, ignorá este mensaje. Tu contraseña no será modificada.
      </p>
    </div>
    """

    payload = {
        "sender": _sender(),
        "to": [{"email": email, "name": name}],
        "subject": "Recuperá tu contraseña — Aura Estudio Pilates",
        "htmlContent": html,
    }

    _send(payload, context="password-reset")


def _send(payload: dict, context: str) -> None:
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        logger.warning(f"BREVO_API_KEY not configured — skipping {context} email")
        return
    try:
        response = requests.post(
            BREVO_SMTP_URL,
            json=payload,
            headers=_brevo_headers(),
            timeout=10,
        )
        if not response.ok:
            logger.error(
                f"Brevo {context} email failed — status {response.status_code}: {response.text}"
            )
            return
        logger.info(f"Brevo {context} email sent to {payload['to'][0]['email']}")
    except requests.RequestException as e:
        logger.error(f"Brevo {context} email failed: {e}")
