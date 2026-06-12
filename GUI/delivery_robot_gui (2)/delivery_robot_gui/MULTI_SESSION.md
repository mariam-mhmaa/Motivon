# Multi-Session Feature - Documentation

## Overview

You can now run the delivery robot GUI with multiple simultaneous login sessions on the same laptop! No need to run `main.py` multiple times.

## How to Use

### Option 1: Open New Session from GUI (Easiest)
1. Run the application once: `python main.py`
2. Once logged in, click **"+ New Session"** button in the top bar
3. A new window opens with the login screen
4. Login with a different user (or same user in different role)
5. Both windows stay active and share the same data!

### Option 2: Traditional Method
If you prefer, you can still run `python main.py` twice from different terminals. Both instances will share the same delivery data.

## Use Case Example

**Scenario**: Test the delivery workflow with one user and one manager

1. **First Window**:
   - Click "User" → Login as `ainour` (password: `ainour5`)
   - Create delivery requests
   - Keep this window open

2. **Same Window - New Session**:
   - Click "User" Dashboard
   - Click "+ New Session" button at top
   - New window opens
   - Click "Manager" → Login as `nour` (password: `nour6`)
   - See requests from ainour automatically
   - Process deliveries

**Result**: You test both user and manager workflows without running the app twice!

## Technical Details

- **Shared Data**: All windows share the same `delivery_system` instance
- **Real-time Updates**: Changes in one window appear in others (with auto-refresh)
- **Window Management**: Windows are tracked in a global list
- **Independent Sessions**: Each window has independent login/logout
- **Offset Positioning**: New windows open offset from existing ones so you can see both

## Features

✅ Multiple simultaneous login sessions  
✅ Shared delivery request database  
✅ Real-time synchronization  
✅ Individual window management  
✅ Clean window tracking and cleanup  

## Button Location

The "+ New Session" button is in the top navigation bar, to the left of the status pills.

**Color**: Green button with "+ New Session" text

