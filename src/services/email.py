import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from jinja2 import Environment, FileSystemLoader

def render_template(invoice):
    env = Environment(loader=FileSystemLoader('templates'))
    tmpl = env.get_template('reminder_email.html')
    return tmpl.render(invoice=invoice)

def send_reminder_email(invoice):
    html_body = render_template(invoice)
    message = Mail(
        from_email='reminders@yourinboxhero.com',
        to_emails=invoice.debtor.email,
        subject=f'Reminder: Invoice {invoice.invoice_number} due {invoice.due_date}',
        html_content=html_body,
    )
    sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    response = sg.send(message)
    if response.status_code >= 400:
        raise Exception(f'SendGrid error {response.status_code}')
    return response