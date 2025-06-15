import scratchattach as sa
import json
import os
import threading
import time

# --- Configuration ---
PROJECT_ID = "1184455002"
BALANCES_FILE = "balances.txt"
AVAILABLE_CURRENCIES = {"bytes", "eckoins", "blockcoins"}
STARTING_BALANCE = 100
SAVE_INTERVAL = 15 # Save data every 15 seconds if it has changed

# --- In-Memory State and Lock ---
data_lock = threading.RLock()
user_balances = {}
data_changed = threading.Event() # Use an Event for thread-safe signaling

# --- Data Management Functions ---

def load_balances_from_file():
    """Loads balances from the file into memory at startup."""
    global user_balances
    with data_lock:
        if not os.path.exists(BALANCES_FILE):
            user_balances = {}
            return
        try:
            with open(BALANCES_FILE, 'r') as f:
                content = f.read()
                user_balances = json.loads(content) if content else {}
            print("Successfully loaded balances from balances.txt")
        except (json.JSONDecodeError, FileNotFoundError):
            print("Could not read balances.txt, starting with empty balances.")
            user_balances = {}

def save_balances_to_file():
    """Saves the current in-memory balances to the file."""
    with data_lock:
        with open(BALANCES_FILE, 'w') as f:
            json.dump(user_balances, f, indent=4)
        print("Data saved to balances.txt")

def periodic_save():
    """A background function to save data periodically."""
    while True:
        # Wait for the data_changed event to be set, with a timeout
        data_changed.wait(timeout=SAVE_INTERVAL)
        
        # If the event was set (not a timeout), save the data
        if data_changed.is_set():
            with data_lock:
                save_balances_to_file()
                data_changed.clear() # Reset the flag after saving

# --- Scratch Connection Setup ---
try:
    # It's better to store your session ID in an environment variable or a separate config file
    session = sa.login_by_id(os.environ.get("SESSION_ID"), username="coockat444")
except Exception as e:
    print(f"Error logging in: {e}")
    exit()

cloud = session.connect_cloud(PROJECT_ID)
client = cloud.requests()
print("Successfully connected to Scratch project!")

# --- Request Handlers (Now Fast and Non-Blocking) ---

@client.request
def getrate(currency_to_get_rate):
    # FIX 1: Always return strings for consistency
    return "1" if str(currency_to_get_rate).lower() in AVAILABLE_CURRENCIES else "Invalid Currency"

@client.request
def getbalance(user, currency):
    user = str(user)
    currency = str(currency).lower()

    if currency not in AVAILABLE_CURRENCIES:
        return "Invalid Currency"

    with data_lock:
        if user not in user_balances:
            print(f"New user '{user}' detected. Creating account.")
            user_balances[user] = {c: STARTING_BALANCE for c in AVAILABLE_CURRENCIES}
            data_changed.set() # FIX 2: Mark data as changed instead of saving immediately
        
        balance = user_balances.get(user, {}).get(currency, 0)
        return str(balance) # FIX 1: Return balance as a string

@client.request
def exchange(start_currency, amount, new_currency):
    requester = client.get_requester()
    
    start_currency_lower = str(start_currency).lower()
    new_currency_lower = str(new_currency).lower()

    if start_currency_lower not in AVAILABLE_CURRENCIES or new_currency_lower not in AVAILABLE_CURRENCIES:
        return "Error: Invalid currency"
    
    try:
        amount_to_exchange = float(amount)
        if amount_to_exchange <= 0: return "Error: Amount must be positive"
    except (ValueError, TypeError):
        return "Error: Invalid amount"

    with data_lock:
        if requester not in user_balances:
            user_balances[requester] = {c: STARTING_BALANCE for c in AVAILABLE_CURRENCIES}
        
        user_wallet = user_balances[requester]
        if user_wallet.get(start_currency_lower, 0) < amount_to_exchange:
            return "Error: Insufficient funds"

        user_wallet[start_currency_lower] -= amount_to_exchange
        user_wallet[new_currency_lower] += amount_to_exchange
        data_changed.set() # FIX 2: Mark data as changed instead of saving immediately

    return f"You converted {amount_to_exchange} {start_currency_lower.title()} to {amount_to_exchange} {new_currency_lower.title()}"

# --- Event Handlers ---
@client.event
def on_ready():
    print("Request handler is running and connected to the cloud.")

# --- Startup ---
load_balances_from_file()

# Start the background saver thread
save_thread = threading.Thread(target=periodic_save, daemon=True)
save_thread.start()

client.start(thread=True)

print("\nScript is running. Press Ctrl+C to stop.")
# The main thread can just sleep or wait, as the work is done in other threads.
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping script... saving final data.")
    # Perform one final save on exit if needed
    if data_changed.is_set():
        save_balances_to_file()
    print("Done.")