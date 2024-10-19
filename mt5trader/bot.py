import MetaTrader5 as mt5
import requests
import time
import logging

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
BOT_API = '7746265731:AAECxGT4uaTpct9ikn0gtCvelJ4VNLyZAH4'
CHANNEL_ID = '-1002277376839'
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

# Function to get the newest Telegram message
def get_latest_message():
    try:
        response = requests.get(TELEGRAM_URL)
        if response.status_code == 200:
            data = response.json()
            messages = data['result']

            if messages:
                latest_message = messages[-1].get('channel_post', {}).get('text', '').strip()
                logging.info(f"Latest message from Telegram: {latest_message}")
                return latest_message

    except Exception as e:
        logging.error(f"Error fetching Telegram messages: {e}")
    return None

# Function to parse the signal
def parse_signal(signal):
    try:
        lines = signal.split('\n')
        logging.info(f"Lines: {lines}")  # Log the message lines after splitting

        # Validate the signal format and extract the trade type
        if len(lines) == 5 and "pair:" in lines[0].lower() and "type:" in lines[1].lower():
            pair = lines[0].split(': ')[1].strip()
            trade_type = lines[1].split(': ')[1].strip().lower()
            logging.info(f"Parsed signal - Pair: {pair}, Type: {trade_type}")
            return trade_type
        else:
            logging.info(f"Message is not a valid trade signal: {signal}")
            return None
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
            'type_filling': mt5.ORDER_FILLING_IOC,
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
            'volume': LOT_SIZE,
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

# Function to send a confirmation message to Telegram after executing a trade
def send_trade_confirmation():
    try:
        confirmation_message = "Signal received! Executing trade on MT5"
        requests.get(f"https://api.telegram.org/bot{BOT_API}/sendMessage?chat_id={CHANNEL_ID}&text={confirmation_message}")
        logging.info("Sent trade confirmation to Telegram.")
    except Exception as e:
        logging.error(f"Error sending trade confirmation: {e}")

# Initialize this variable to keep track of the last processed message
# Initialize this variable to keep track of the last processed signal
last_processed_message = None

def main():
    global last_processed_message
    logging.info("Listening for signals...")

    while True:
        latest_message = get_latest_message()

        if latest_message:
            # Check if the message is the confirmation message and ignore it
            if "Signal received! Executing trade on MT5" in latest_message:
                logging.info("Confirmation message detected, ignoring it.")
                time.sleep(1)  # Wait before checking again
                continue
            
            # Check if the message has already been processed (duplicate check)
            if latest_message == last_processed_message:
                logging.info("Duplicate message detected, no action taken.")
                time.sleep(1)  # Wait before checking again
                continue

            # Parse and validate the new message (signal)
            trade_type = parse_signal(latest_message)
            if trade_type:
                open_trade_position = get_open_trade()

                # If there's an open trade in the opposite direction, close it first
                if open_trade_position:
                    if (trade_type == "buy" and open_trade_position.type == mt5.ORDER_TYPE_SELL) or \
                        (trade_type == "sell" and open_trade_position.type == mt5.ORDER_TYPE_BUY):

                        logging.info(f"Closing current {open_trade_position.type} trade...")
                        close_result = close_trade(open_trade_position)

                        if close_result and close_result.retcode == mt5.TRADE_RETCODE_DONE:
                            logging.info("Trade closed successfully.")
                            time.sleep(2)  # Pause before opening the new trade
                            open_trade(trade_type)
                            send_trade_confirmation()

                            # Mark the message as processed
                            last_processed_message = latest_message
                    else:
                        logging.info(f"Trade already open in {trade_type} direction, no action taken.")
                else:
                    logging.info(f"Opening new {trade_type} trade...")
                    open_trade(trade_type)
                    send_trade_confirmation()

                    # Mark the message as processed
                    last_processed_message = latest_message

        time.sleep(0.1)  # Check for new signals every 1 second

if __name__ == "__main__":
    main()


