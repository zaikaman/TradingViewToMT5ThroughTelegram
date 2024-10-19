import MetaTrader5 as mt5
import requests
import time
import logging
from datetime import datetime

# Setup logging with both file and console output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()  # This will print to the console
    ]
)

# Telegram bot details
BOT_API = ''
CHANNEL_ID = ''
TELEGRAM_URL = f'https://api.telegram.org/bot{BOT_API}/getUpdates'

# MT5 configuration
SYMBOL = "BTCUSD"
LOT_SIZE = 0.05  # 0.05 lots per trade
TIMEFRAME = mt5.TIMEFRAME_M1  # 1-minute timeframe

# Initialize MT5
if not mt5.initialize():
    logging.error("MT5 initialization failed")
    quit()
else:
    logging.info("MT5 initialized successfully")

# Text file to store processed messages' update_id and content
PROCESSED_MESSAGES_FILE = "processed_messages.txt"

# Biến lưu lại update_id cuối cùng đã kiểm tra
last_update_id = 0

# Function to read processed message ids from the file
def read_processed_messages():
    processed_ids = set()
    try:
        with open(PROCESSED_MESSAGES_FILE, "r") as file:
            for line in file:
                # Only read update_id from each line
                update_id = line.strip()  # Remove any extra whitespace or newlines
                processed_ids.add(int(update_id))
    except FileNotFoundError:
        logging.info(f"{PROCESSED_MESSAGES_FILE} not found, starting fresh.")
    return processed_ids

# Function to save only the update_id of processed messages
def save_processed_message(update_id):
    try:
        with open(PROCESSED_MESSAGES_FILE, "a") as file:
            # Save only the update_id to the file
            file.write(f"{update_id}\n")
        logging.info(f"Saved processed message id: {update_id}")
    except Exception as e:
        logging.error(f"Error saving processed message id: {e}")

# Function to get Telegram signals
def get_telegram_signal(processed_ids):
    global last_update_id
    try:
        response = requests.get(TELEGRAM_URL)
        if response.status_code == 200:
            data = response.json()
            messages = data['result']
            logging.info(f"Received {len(messages)} messages from Telegram")
            
            for message in reversed(messages):
                update_id = message.get('update_id')

                # Skip messages that are already processed
                if update_id in processed_ids:
                    logging.info(f"Skipping already processed message with update_id: {update_id}")
                    continue

                # Get message content
                text = message.get('channel_post', {}).get('text', '')
                text = text.strip()

                # Split the message into lines
                lines = text.split('\n')

                # Ensure there are exactly 5 lines in the message
                if len(lines) != 5:
                    logging.info(f"Skipping message with {len(lines)} lines: {text}")
                    continue

                # Check if the message contains a valid signal
                if "pair:" in lines[0].lower() and "type:" in lines[1].lower():
                    logging.info(f"Valid signal found: {text}")
                    
                    # Save the correct update_id
                    save_processed_message(update_id)
                    
                    # Reload the processed_ids to ensure it's updated
                    processed_ids.add(update_id)  # Update the set directly instead of reading from the file
                    return text
                else:
                    logging.info(f"No valid signal in message: {text}")
                    
    except Exception as e:
        logging.error(f"Error fetching Telegram messages: {e}")

# Function to parse the signal
def parse_signal(signal):
    try:
        lines = signal.split('\n')
        logging.info(f"Lines: {lines}")  # Log the message lines after splitting
        pair = lines[0].split(': ')[1].strip()
        trade_type = lines[1].split(': ')[1].strip().lower()
        logging.info(f"Parsed signal - Pair: {pair}, Type: {trade_type}")
        return trade_type
    except Exception as e:
        logging.error(f"Error parsing signal: {e}")
        return None

# Function to check if there are open trades
def get_open_trade():
    try:
        trades = mt5.positions_get(symbol=SYMBOL)
        if trades:
            logging.info(f"Open trade found: {trades[0]}")
            return trades[0]
        logging.info("No open trades found.")
        return None
    except Exception as e:
        logging.error(f"Error getting open trades: {e}")
        return None

# Function to close an existing trade
def close_trade(trade):
    try:
        trade_type = mt5.ORDER_TYPE_SELL if trade.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        close_request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': trade.symbol,
            'volume': trade.volume,
            'type': trade_type,
            'position': trade.ticket,
            'price': mt5.symbol_info_tick(SYMBOL).bid if trade_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(SYMBOL).ask,
            'deviation': 20,
            'magic': 234000,
            'comment': "Closing trade",
            'type_filling': mt5.ORDER_FILLING_IOC,  # Changed from FOK to IOC
        }
        result = mt5.order_send(close_request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Failed to close trade: {result}")
        else:
            logging.info(f"Close trade result: {result}")
        return result
    except Exception as e:
        logging.error(f"Error closing trade: {e}")
        return None

# Function to open a new trade
def open_trade(trade_type):
    try:
        price = mt5.symbol_info_tick(SYMBOL).ask if trade_type == "buy" else mt5.symbol_info_tick(SYMBOL).bid
        order_type = mt5.ORDER_TYPE_BUY if trade_type == "buy" else mt5.ORDER_TYPE_SELL
        
        trade_request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'magic': 234000,
            'symbol': SYMBOL,
            'volume': LOT_SIZE,  # Use predefined LOT_SIZE
            'price': price,
            'deviation': 20,
            'type': order_type,
            'type_filling': mt5.ORDER_FILLING_IOC,
            'type_time': mt5.ORDER_TIME_GTC,
            'comment': f'{trade_type} trade',
        }

        result = mt5.order_send(trade_request)
        logging.info(f"Open trade result: {result}")
        return result
    except Exception as e:
        logging.error(f"Error opening trade: {e}")
        return None

# Main loop
def main():
    logging.info("Listening for signals...")
    
    # Read processed messages before starting
    processed_ids = read_processed_messages()

    while True:
        signal = get_telegram_signal(processed_ids)
        if signal:
            trade_type = parse_signal(signal)
            if trade_type:
                open_trade_position = get_open_trade()

                # If there's an open trade, check if it's opposite to the new signal
                if open_trade_position:
                    if (trade_type == "buy" and open_trade_position.type == mt5.ORDER_TYPE_SELL) or \
                        (trade_type == "sell" and open_trade_position.type == mt5.ORDER_TYPE_BUY):
                        
                        logging.info(f"Closing current {open_trade_position.type} trade...")
                        close_result = close_trade(open_trade_position)

                        # Ensure the trade was closed successfully
                        if close_result and close_result.retcode == mt5.TRADE_RETCODE_DONE:
                            logging.info("Trade closed successfully.")
                            time.sleep(2)  # Give MT5 time to process the trade closure
                            
                            # Now open the new trade
                            logging.info(f"Opening new {trade_type} trade...")
                            open_trade(trade_type)
                        else:
                            logging.error(f"Failed to close trade: {close_result}")
                            continue  # Skip to the next iteration if trade close fails
                    else:
                        logging.info(f"Trade already open in {trade_type} direction, no action taken.")
                else:
                    # No open trade, open a new one
                    logging.info(f"Opening new {trade_type} trade...")
                    open_trade(trade_type)

        time.sleep(1)  # Check for new signals every 1 seconds

if __name__ == "__main__":
    main()

