# core/cleaning_tracker.py
import hashlib
import json
import os

TRACKER_FILE = "cleaning_state.json"

# Load existing state
def load_cleaning_state():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r") as f:
            return json.load(f)
    return {}

# Save updated state
def save_cleaning_state(state):
    with open(TRACKER_FILE, "w") as f:
        json.dump(state, f, indent=4)

# Compute hash of file content
def file_hash(filepath):
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None

# Check if file is already cleaned
def is_already_cleaned(filepath):
    state = load_cleaning_state()
    h = file_hash(filepath)
    return state.get(filepath) == h

# Mark file as cleaned
def mark_cleaned(filepath):
    state = load_cleaning_state()
    h = file_hash(filepath)
    if h:
        state[filepath] = h
        save_cleaning_state(state)
