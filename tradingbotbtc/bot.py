import imaplib
import email
from email.header import decode_header
import telebot
import time

# Telegram bot token and chat ID
TOKEN = ''
CHAT_ID = ''  # Replace with your Telegram chat ID

# Initialize Telegram bot
bot = telebot.TeleBot(TOKEN)

# Gmail IMAP setup
IMAP_SERVER = ""
IMAP_USER = ""  
IMAP_PASS = ""   

# Email checking interval (in seconds)
CHECK_INTERVAL = 1  # Check every 30 seconds

# Initial balance and leverage
balance = 1000.0
open_trade = None  # Stores the details of an open trade if any
leverage = 10  # Assume 10x leverage for futures trading

# Function to reset balance
def reset_balance():
    global balance, open_trade
    balance = 1000.0
    open_trade = None  # Clear any open trades
    bot.send_message(CHAT_ID, "Balance has been reset to 1000 USD.")

# Telegram command handler for /reset
@bot.message_handler(commands=['reset'])
def handle_reset(message):
    if message.chat.id == int(CHAT_ID):
        reset_balance()
    else:
        bot.send_message(message.chat.id, "Unauthorized command.")

def check_email():
    global balance, open_trade

    # Connect to the Gmail server
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(IMAP_USER, IMAP_PASS)
    
    # Select the inbox folder
    mail.select("inbox")

    # Search for unseen emails
    status, messages = mail.search(None, 'UNSEEN')
    email_ids = messages[0].split()

    if not email_ids:
        return

    for email_id in email_ids:
        # Fetch the email by ID
        res, msg = mail.fetch(email_id, "(RFC822)")
        for response_part in msg:
            if isinstance(response_part, tuple):
                # Parse the email content
                msg = email.message_from_bytes(response_part[1])

                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding)

                # Extract email body
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            process_email(subject, body)
                else:
                    body = msg.get_payload(decode=True).decode()
                    process_email(subject, body)

def process_email(subject, body):
    global balance, open_trade

    try:
        # Check if the email contains #RESET
        if "#RESET" in body:
            reset_balance()  # Reset balance via email
            return  # Exit early after reset

        # Check if body contains #BTCUSD
        if "#BTCUSD" in body:
            lines = body.strip().split("\n")
            pair = lines[0].split(": ")[1].strip()
            trade_type = lines[1].split(": ")[1].strip().upper()  # Convert trade_type to uppercase
            entry = float(lines[2].split(": ")[1].strip())
            size = float(lines[3].split(": ")[1].replace(" USD", "").strip())

            # Adjust size based on leverage
            leveraged_size = size * leverage

            # Process the trade
            if trade_type == "BUY":  # LONG in futures
                if open_trade is None:
                    # Open a new LONG trade
                    open_trade = {"type": "LONG", "entry": entry, "size": leveraged_size}
                elif open_trade["type"] == "SHORT":
                    # Close the SHORT trade and calculate profit
                    profit = (open_trade["entry"] - entry) * (open_trade["size"] / open_trade["entry"])
                    balance += profit
                    open_trade = None  # Close the trade
                    # Open a new LONG trade
                    open_trade = {"type": "LONG", "entry": entry, "size": leveraged_size}

            elif trade_type == "SELL":  # SHORT in futures
                if open_trade is None:
                    # Open a new SHORT trade
                    open_trade = {"type": "SHORT", "entry": entry, "size": leveraged_size}
                elif open_trade["type"] == "LONG":
                    # Close the LONG trade and calculate profit
                    profit = (entry - open_trade["entry"]) * (open_trade["size"] / open_trade["entry"])
                    balance += profit
                    open_trade = None  # Close the trade
                    # Open a new SHORT trade
                    open_trade = {"type": "SHORT", "entry": entry, "size": leveraged_size}

            # Format the email body and balance without the subject and extra newline
            message = f"{body.strip()}\nBALANCE: {balance:.2f} USD"

            # Send the email content to Telegram
            bot.send_message(CHAT_ID, message)
        else:
            print("Email does not contain #BTCUSD or #RESET, skipping...")

    except Exception as e:
        print(f"Error processing message: {e}")

if __name__ == "__main__":
    # Start polling for Telegram messages in a separate thread
    import threading
    telegram_thread = threading.Thread(target=bot.polling, args=(), daemon=True)
    telegram_thread.start()

    # Main email checking loop
    while True:
        try:
            check_email()
            print("Checked emails, waiting for next interval...")
        except Exception as e:
            print(f"Error checking emails: {e}")
        
        # Wait for the defined interval before checking again
        time.sleep(CHECK_INTERVAL)
