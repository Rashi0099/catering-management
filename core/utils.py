import threading
from django.core.mail import send_mail
import requests

def send_mail_background(subject, message, from_email, recipient_list, **kwargs):
    """Sends email asynchronously to prevent UI blocking."""
    thread = threading.Thread(
        target=send_mail,
        args=(subject, message, from_email, recipient_list),
        kwargs=kwargs
    )
    thread.start()

def get_request_background(url, params=None, **kwargs):
    """Makes a GET request asynchronously."""
    thread = threading.Thread(
        target=requests.get,
        args=(url,),
        kwargs={'params': params, **kwargs}
    )
    thread.start()
