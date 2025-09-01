from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
import sqlite3
import os
import uuid
import re

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')
DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # Create members table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            handicap REAL NOT NULL,
            gender TEXT CHECK(gender IN ('Male', 'Female')) DEFAULT 'Male',
            gross_win BOOLEAN DEFAULT 0,
            tournaments_played INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0
        )
    ''')
    
    # Check if old tournaments table exists and migrate if needed
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tournaments'")
    table_exists = cursor.fetchone() is not None
    
    if table_exists:
        # Check if it has the old schema (member_id, score columns)
        cursor = conn.execute("PRAGMA table_info(tournaments)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'member_id' in columns and 'score' in columns:
            # Old schema detected - need to migrate
            print("Migrating old tournament data...")
            
            # Rename old table
            conn.execute("ALTER TABLE tournaments RENAME TO old_tournaments")
            
            # Create new tournaments table
            conn.execute('''
                CREATE TABLE tournaments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    description TEXT,
                    finalized BOOLEAN DEFAULT 0
                )
            ''')
            
            # Create tournament_scores table
            conn.execute('''
                CREATE TABLE tournament_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER NOT NULL,
                    member_id INTEGER NOT NULL,
                    hole1 INTEGER,
                    hole2 INTEGER,
                    hole3 INTEGER,
                    hole4 INTEGER,
                    hole5 INTEGER,
                    hole6 INTEGER,
                    hole7 INTEGER,
                    hole8 INTEGER,
                    hole9 INTEGER,
                    hole10 INTEGER,
                    hole11 INTEGER,
                    hole12 INTEGER,
                    hole13 INTEGER,
                    hole14 INTEGER,
                    hole15 INTEGER,
                    hole16 INTEGER,
                    hole17 INTEGER,
                    hole18 INTEGER,
                    total_score INTEGER,
                    FOREIGN KEY (tournament_id) REFERENCES tournaments (id),
                    FOREIGN KEY (member_id) REFERENCES members (id)
                )
            ''')
            
            # Migrate old data
            # Create a default tournament for existing scores
            from datetime import date
            today = date.today().isoformat()
            conn.execute(
                "INSERT INTO tournaments (name, date, description) VALUES (?, ?, ?)",
                ("Migrated Tournament", today, "Tournament created from old data")
            )
            
            # Get the new tournament ID
            tournament_id = conn.lastrowid
            
            # Migrate old scores to new structure
            conn.execute('''
                INSERT INTO tournament_scores (tournament_id, member_id, total_score)
                SELECT ?, member_id, score FROM old_tournaments
            ''', (tournament_id,))
            
            # Drop old table
            conn.execute("DROP TABLE old_tournaments")
            
            print(f"Migration complete. Old scores moved to tournament: 'Migrated Tournament'")
    
    else:
        # Create new tournaments table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                finalized BOOLEAN DEFAULT 0
            )
        ''')
        
        # Create groups table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                secure_token TEXT UNIQUE,
                tee_time TEXT,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id)
            )
        ''')
        
        # Create group_members table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                tournament_id INTEGER NOT NULL,
                FOREIGN KEY (group_id) REFERENCES groups (id),
                FOREIGN KEY (member_id) REFERENCES members (id),
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id),
                UNIQUE(member_id, tournament_id)
            )
        ''')
        
        # Create tournament_scores table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tournament_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                hole1 INTEGER,
                hole2 INTEGER,
                hole3 INTEGER,
                hole4 INTEGER,
                hole5 INTEGER,
                hole6 INTEGER,
                hole7 INTEGER,
                hole8 INTEGER,
                hole9 INTEGER,
                hole10 INTEGER,
                hole11 INTEGER,
                hole12 INTEGER,
                hole13 INTEGER,
                hole14 INTEGER,
                hole15 INTEGER,
                hole16 INTEGER,
                hole17 INTEGER,
                hole18 INTEGER,
                total_score INTEGER,
                net_handicap REAL,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id),
                FOREIGN KEY (member_id) REFERENCES members (id)
            )
        ''')
        
        # Create honorable mentions table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS honorable_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                honor_type TEXT NOT NULL,
                honor_type_name TEXT,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id),
                FOREIGN KEY (member_id) REFERENCES members (id),
                UNIQUE(tournament_id, honor_type)
            )
        ''')
    # Ensure net_handicap column exists in tournament_scores (migration for older DBs)
    try:
        conn.execute("ALTER TABLE tournament_scores ADD COLUMN net_handicap REAL")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    # Ensure honorable_mentions table exists (for existing databases)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS honorable_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            honor_type TEXT NOT NULL,
            honor_type_name TEXT,
            balls_awarded INTEGER DEFAULT 0,
            FOREIGN KEY (tournament_id) REFERENCES tournaments (id),
            FOREIGN KEY (member_id) REFERENCES members (id),
            UNIQUE(tournament_id, honor_type)
        )
    ''')
    try:
        conn.execute("ALTER TABLE honorable_mentions ADD COLUMN honor_type_name TEXT")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    # Ensure points column exists in members (for older DBs)
    try:
        conn.execute("ALTER TABLE members ADD COLUMN points INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    # Ensure balls_awarded column exists (for older DBs)
    try:
        conn.execute("ALTER TABLE honorable_mentions ADD COLUMN balls_awarded INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists
        pass

    # Create tournament_honor_types table to store customizable honor names
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tournament_honor_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            original_honor_type TEXT NOT NULL,
            custom_name TEXT NOT NULL,
            display_order INTEGER,
            FOREIGN KEY (tournament_id) REFERENCES tournaments (id),
            UNIQUE(tournament_id, original_honor_type)
        )
    ''')
    
    # Ensure secure_token column exists in groups table (migration for older DBs)
    try:
        conn.execute("ALTER TABLE groups ADD COLUMN secure_token TEXT")
        print("Added secure_token column to groups table")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    # Ensure tee_time column exists in groups table
    try:
        conn.execute("ALTER TABLE groups ADD COLUMN tee_time TEXT")
        print("Added tee_time column to groups table")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    # Generate secure tokens for existing groups that don't have them
    try:
        groups_needing_tokens = conn.execute('SELECT id FROM groups WHERE secure_token IS NULL').fetchall()
        for group in groups_needing_tokens:
            token = str(uuid.uuid4())
            conn.execute('UPDATE groups SET secure_token = ? WHERE id = ?', (token, group['id']))
            print(f"Generated token for group {group['id']}: {token}")
    except Exception as e:
        print(f"Error generating tokens: {e}")
    
    # Add unique constraint if it doesn't exist (best effort)
    try:
        # This will only work if we're recreating the table or if SQLite supports it
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_secure_token ON groups(secure_token)")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def reset_members_autoincrement():
    """Reset the auto-increment counter for members table when all members are deleted"""
    conn = get_db_connection()
    # Check if there are any members left
    count = conn.execute('SELECT COUNT(*) FROM members').fetchone()[0]
    if count == 0:
        # Reset the auto-increment counter
        conn.execute('DELETE FROM sqlite_sequence WHERE name="members"')
        conn.commit()
    conn.close()

def get_handicap_range(handicap):
    """Get the handicap range string based on current handicap"""
    if handicap <= 9:
        return "0-9"
    elif handicap <= 15:
        return "10-15"
    elif handicap <= 21:
        return "16-21"
    elif handicap <= 26:
        return "22-26"
    elif handicap <= 32:
        return "27-32"
    else:
        return "33-38"

def calculate_position_adjustment(current_handicap, position):
    """
    Calculate position-based handicap adjustment for top 3 finishers.
    
    Args:
        current_handicap: Current handicap of the player
        position: 1 for 1st place, 2 for 2nd place, 3 for 3rd place
    
    Returns:
        handicap_adjustment: Negative number (decrease in handicap)
    """
    # Get handicap range
    handicap_range = get_handicap_range(current_handicap)
    print(f"      Position adjustment calculation: handicap={current_handicap}, range={handicap_range}, position={position}")
    
    # Position-based adjustments for top 3 places
    if position == 1:  # 1st Place
        if handicap_range == "0-9":
            adjustment = -1
        elif handicap_range == "10-15":
            adjustment = -2
        elif handicap_range == "16-21":
            adjustment = -3
        elif handicap_range == "22-26":
            adjustment = -4
        elif handicap_range == "27-32":
            adjustment = -5
        elif handicap_range == "33-38":
            adjustment = -6
    elif position == 2:  # 2nd Place
        if handicap_range == "0-9":
            adjustment = 0
        elif handicap_range == "10-15":
            adjustment = -1
        elif handicap_range == "16-21":
            adjustment = -2
        elif handicap_range == "22-26":
            adjustment = -3
        elif handicap_range == "27-32":
            adjustment = -4
        elif handicap_range == "33-38":
            adjustment = -5
    elif position == 3:  # 3rd Place
        if handicap_range == "0-9":
            adjustment = 0
        elif handicap_range == "10-15":
            adjustment = 0
        elif handicap_range == "16-21":
            adjustment = -1
        elif handicap_range == "22-26":
            adjustment = -2
        elif handicap_range == "27-32":
            adjustment = -3
        elif handicap_range == "33-38":
            adjustment = -4
    else:
        adjustment = 0  # No adjustment for positions beyond 3rd
    
    print(f"      Position adjustment result: {adjustment}")
    return adjustment

def calculate_strokes_adjustment(current_handicap, strokes_under_72):
    """
    Calculate strokes-under-72 based handicap adjustment.
    
    Args:
        current_handicap: Current handicap of the player
        strokes_under_72: Number of strokes under 72 (negative for over 72)
    
    Returns:
        handicap_adjustment: Negative number (decrease in handicap)
    """
    print(f"      Strokes adjustment calculation: handicap={current_handicap}, strokes_under_72={strokes_under_72}")
    
    # Define handicap adjustment rules for strokes under 72
    handicap_adjustments = {
        "0-9": {
            1: 0, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2,
            7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3
        },
        "10-15": {
            1: 0, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2,
            7: 2, 8: 3, 9: 3, 10: 3, 11: 4, 12: 4
        },
        "16-21": {
            1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3,
            7: 4, 8: 4, 9: 4, 10: 5, 11: 6, 12: 6
        },
        "22-26": {
            1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 4,
            7: 5, 8: 6, 9: 6, 10: 6, 11: 8, 12: 8
        },
        "27-32": {
            1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6,
            7: 7, 8: 8, 9: 9, 10: 10, 11: 11, 12: 12
        }
    }
    
    # Get handicap range
    handicap_range = get_handicap_range(current_handicap)
    print(f"      Handicap range: {handicap_range}")
    
    # If handicap is 33-38, no strokes-based adjustment
    if handicap_range == "33-38":
        print(f"      Handicap 33-38 - no strokes adjustment")
        return 0
    
    # For other ranges, use strokes under 72
    if strokes_under_72 <= 0:
        print(f"      Strokes under 72 <= 0 - no adjustment")
        return 0  # No adjustment for scores of 72 or higher
    
    # Cap strokes under at 12 for the lookup
    strokes_under = min(strokes_under_72, 12)
    print(f"      Strokes under (capped at 12): {strokes_under}")
    
    # Get adjustment from the rules
    adjustment = handicap_adjustments[handicap_range].get(strokes_under, 0)
    print(f"      Raw adjustment from rules: {adjustment}")
    
    final_adjustment = -adjustment  # Return negative for handicap decrease
    print(f"      Final strokes adjustment: {final_adjustment}")
    return final_adjustment

def calculate_total_handicap_adjustment(current_handicap, strokes_under_72, position):
    """
    Calculate total handicap adjustment combining position and strokes under 72.
    
    Args:
        current_handicap: Current handicap of the player
        strokes_under_72: Number of strokes under 72 (negative for over 72)
        position: 1 for 1st place, 2 for 2nd place, 3 for 3rd place
    
    Returns:
        total_adjustment: Combined adjustment from both position and strokes
    """
    # Calculate position-based adjustment
    position_adjustment = calculate_position_adjustment(current_handicap, position)
    
    # Calculate strokes-based adjustment
    strokes_adjustment = calculate_strokes_adjustment(current_handicap, strokes_under_72)
    
    # Combine both adjustments
    total_adjustment = position_adjustment + strokes_adjustment
    
    return total_adjustment

def apply_handicap_adjustments(tournament_id):
    """
    Apply handicap adjustments for a finalized tournament.
    This function should be called when a tournament is finalized.
    """
    print(f"\n=== STARTING HANDICAP ADJUSTMENTS FOR TOURNAMENT {tournament_id} ===")
    conn = get_db_connection()
    adjustments_log = []
    
    # Get all scores for this tournament with member details - ORDER BY total_score for tie-breaking
    scores = conn.execute('''
        SELECT ts.*, m.name, m.gender, m.id as member_id, m.gross_win, m.handicap, ts.total_score, ts.net_handicap, m.tournaments_played
        FROM tournament_scores ts
        JOIN members m ON ts.member_id = m.id
        WHERE ts.tournament_id = ?
        ORDER BY ts.total_score
    ''', (tournament_id,)).fetchall()
    
    print(f"Found {len(scores)} total scores for tournament")
    for score in scores:
        print(f"  - {score['name']}: Gross={score['total_score']}, Handicap={score['handicap']}, Net={score['total_score'] - score['handicap'] if score['total_score'] and score['handicap'] else 'N/A'}, Gross Win={score['gross_win']}, Tournaments={score['tournaments_played']}")
    
    if not scores:
        print("No scores found - exiting")
        conn.close()
        return
    
    # Gross leaderboard - includes all players (the website logic determines who appears in gross vs net)
    gross_scores = scores  # Include all scores for gross leaderboard
    print(f"\n--- GROSS LEADERBOARD SETUP ---")
    print(f"All scores for gross leaderboard: {len(gross_scores)}")
    for score in gross_scores:
        print(f"  - {score['name']}: Gross={score['total_score']}, Gross Win Flag={score['gross_win']}")
    
    # Separate by gender for gross scores
    gross_male_scores = [score for score in gross_scores if score['gender'] == 'Male']
    gross_female_scores = [score for score in gross_scores if score['gender'] == 'Female']
    print(f"Gross male scores: {len(gross_male_scores)}")
    print(f"Gross female scores: {len(gross_female_scores)}")
    
    # Sort gross scores by total_score (gross score) to get actual winners
    gross_male_scores.sort(key=lambda x: x['total_score'] if x['total_score'] is not None else float('inf'))
    gross_female_scores.sort(key=lambda x: x['total_score'] if x['total_score'] is not None else float('inf'))
    
    # Get the winners of gross leaderboards (1st place in each gender)
    # These are the #1 players on the gross leaderboard display
    gross_male_winners = gross_male_scores[:1] if gross_male_scores else []
    gross_female_winners = gross_female_scores[:1] if gross_female_scores else []
    print(f"Gross male winners (#1 on gross leaderboard): {[w['name'] for w in gross_male_winners]}")
    print(f"Gross female winners (#1 on gross leaderboard): {[w['name'] for w in gross_female_winners]}")
    
    # Create list of winner member IDs to exclude from net leaderboards
    # These are the gross champions of THIS tournament who should not get net position adjustments
    this_tournament_gross_winners = [score['member_id'] for score in gross_male_winners + gross_female_winners]
    print(f"Gross winner IDs of THIS tournament to exclude from net position adjustments: {this_tournament_gross_winners}")
    
    # Net leaderboard excludes gross winners of THIS tournament and members with 3 or fewer tournaments played
    net_scores = [score for score in scores if score['member_id'] not in this_tournament_gross_winners and (score['tournaments_played'] if score['tournaments_played'] is not None else 0) > 3]
    print(f"\n--- NET LEADERBOARD SETUP ---")
    print(f"Net scores (excluding THIS tournament's gross winners and <=3 tournaments): {len(net_scores)}")
    for score in net_scores:
        print(f"  - {score['name']}: Gross={score['total_score']}, Handicap={score['handicap']}, Net={score['total_score'] - score['handicap'] if score['total_score'] and score['handicap'] else 'N/A'}")
    
    # Net leaderboard INCLUDING gross winners (for strokes-under-72 adjustment) - excludes only members with 3 or fewer tournaments played
    # Note: Gross winners of THIS tournament ARE included for strokes adjustments
    net_scores_including_gross = [score for score in scores if (score['tournaments_played'] if score['tournaments_played'] is not None else 0) > 3]
    print(f"Net scores including gross winners (for strokes adjustment): {len(net_scores_including_gross)}")
    
    # Separate net scores by gender (excluding gross winners for position adjustments)
    net_male_scores = [score for score in net_scores if score['gender'] == 'Male']
    net_female_scores = [score for score in net_scores if score['gender'] == 'Female']
    print(f"Net male scores (position adjustments): {len(net_male_scores)}")
    print(f"Net female scores (position adjustments): {len(net_female_scores)}")
    
    # Separate net scores INCLUDING gross winners by gender (for strokes-under-72 adjustments)
    net_male_scores_including_gross = [score for score in net_scores_including_gross if score['gender'] == 'Male']
    net_female_scores_including_gross = [score for score in net_scores_including_gross if score['gender'] == 'Female']
    print(f"Net male scores (strokes adjustments): {len(net_male_scores_including_gross)}")
    print(f"Net female scores (strokes adjustments): {len(net_female_scores_including_gross)}")

    # Process position-based adjustments for net leaderboard (excluding gross winners)
    print(f"\n--- POSITION-BASED ADJUSTMENTS ---")
    for gender_scores in [net_male_scores, net_female_scores]:
        gender = "Male" if gender_scores == net_male_scores else "Female"
        if not gender_scores:
            print(f"No {gender} scores for position adjustments")
            continue
        
        print(f"\nProcessing {gender} position adjustments:")
        
        # Create tuples exactly like the template does: (score, net_score)
        calculated_net_scores = []
        for score in gender_scores:
            if score['total_score'] is not None and score['handicap'] is not None:
                net_score = int(score['total_score'] - score['handicap'])  # Use int() like template
                calculated_net_scores.append((score, net_score))
                print(f"  - {score['name']}: Gross={score['total_score']}, Handicap={score['handicap']}, Net={net_score}")
        
        # Sort by net score (attribute 1 of the tuple) - exactly like template
        # The stable sort preserves the original gross score order for tie-breaking
        calculated_net_scores.sort(key=lambda x: x[1])
        print(f"Sorted by net score: {[(s['name'], n) for s, n in calculated_net_scores]}")
        
        top_3 = calculated_net_scores[:3]
        print(f"Top 3 for position adjustments: {[(s['name'], n) for s, n in top_3]}")
        
        # Calculate adjustments for each position
        for i, (score, net_score) in enumerate(top_3, 1):
            original_handicap = score['handicap']  # This is the handicap at tournament start
            total_score = score['total_score']
            net_score = total_score - original_handicap
            print(f"\n  Position {i}: {score['name']}")
            print(f"    Original handicap (tournament start): {original_handicap}")
            print(f"    Total score: {total_score}")
            print(f"    Net score: {net_score}")
            
            # Only position-based adjustment for the traditional net leaderboard
            position_adjustment = calculate_position_adjustment(original_handicap, i)
            print(f"    Position adjustment: {position_adjustment}")
            
            # Apply adjustment (ensure handicap doesn't go below 0)
            new_handicap = max(0, original_handicap + position_adjustment)
            print(f"    New handicap: {new_handicap} (was {original_handicap})")
            
            # Update member's handicap
            conn.execute(
                'UPDATE members SET handicap = ? WHERE id = ?',
                (new_handicap, score['member_id'])
            )
            print(f"    Updated member {score['member_id']} handicap to {new_handicap}")
            
            # Also save the net_handicap used for this tournament score
            conn.execute(
                'UPDATE tournament_scores SET net_handicap = ? WHERE id = ?',
                (original_handicap, score['id'])
            )
            print(f"    Saved net_handicap {original_handicap} to tournament score {score['id']}")
            
            adjustments_log.append({
                "name": score['name'],
                "old": original_handicap,
                "new": new_handicap,
                "adjustment": new_handicap - original_handicap,  # Total adjustment is the difference
                "reason": f"Net {i}{'st' if i == 1 else 'nd' if i == 2 else 'rd'} place"
            })
    
    # Process strokes-under-72 adjustments for net leaderboard INCLUDING gross winners
    print(f"\n--- STROKES-UNDER-72 ADJUSTMENTS ---")
    for gender_scores in [net_male_scores_including_gross, net_female_scores_including_gross]:
        gender = "Male" if gender_scores == net_male_scores_including_gross else "Female"
        if not gender_scores:
            print(f"No {gender} scores for strokes adjustments")
            continue
        
        print(f"\nProcessing {gender} strokes-under-72 adjustments:")
        
        # Create tuples for all eligible players: (score, net_score)
        all_calculated_net_scores = []
        for score in gender_scores:
            if score['total_score'] is not None and score['handicap'] is not None:
                net_score = int(score['total_score'] - score['handicap'])
                all_calculated_net_scores.append((score, net_score))
                print(f"  - {score['name']}: Gross={score['total_score']}, Handicap={score['handicap']}, Net={net_score}")
        
        # Apply strokes-under-72 adjustment to ALL players with net scores under 72
        for score, net_score in all_calculated_net_scores:
            strokes_under_72 = 72 - net_score
            print(f"\n  Checking {score['name']}: Net={net_score}, Strokes under 72={strokes_under_72}")
            
            if strokes_under_72 > 0:  # Only apply if net score is under 72
                print(f"    Net score under 72 - checking for adjustment")
                
                # Use the original handicap from tournament start (stored in score['handicap'])
                original_handicap = score['handicap']
                print(f"    Original handicap (tournament start): {original_handicap}")
                
                strokes_adjustment = calculate_strokes_adjustment(original_handicap, strokes_under_72)
                print(f"    Strokes adjustment: {strokes_adjustment}")
                
                if strokes_adjustment != 0:  # Only update if there's an actual adjustment
                    # Get current handicap to see what it was after position adjustment
                    current_handicap = conn.execute(
                        'SELECT handicap FROM members WHERE id = ?',
                        (score['member_id'],)
                    ).fetchone()['handicap']
                    print(f"    Current handicap (after position adjustment): {current_handicap}")
                    
                    # Apply strokes adjustment on top of current handicap
                    new_handicap = max(0, current_handicap + strokes_adjustment)
                    print(f"    New handicap: {new_handicap} (was {current_handicap})")
                    
                    conn.execute(
                        'UPDATE members SET handicap = ? WHERE id = ?',
                        (new_handicap, score['member_id'])
                    )
                    print(f"    Updated member {score['member_id']} handicap to {new_handicap}")
                    
                    # Check if this player already has a log entry (from position adjustment)
                    existing_log = next((log for log in adjustments_log if log['name'] == score['name']), None)
                    if existing_log:
                        # Update existing log entry to include strokes adjustment
                        existing_log['new'] = new_handicap
                        existing_log['adjustment'] = new_handicap - original_handicap  # Total adjustment is the difference
                        existing_log['reason'] = existing_log['reason'] + f" + {strokes_under_72} strokes under 72"
                        print(f"    Updated existing log entry - total adjustment: {existing_log['adjustment']}")
                    else:
                        # Add new log entry for strokes-only adjustment
                        adjustments_log.append({
                            "name": score['name'],
                            "old": original_handicap,  # Original handicap at tournament start
                            "new": new_handicap,
                            "adjustment": new_handicap - original_handicap,  # Total adjustment is the difference
                            "reason": f"{strokes_under_72} strokes under 72"
                        })
                        print(f"    Added new log entry for strokes-only adjustment")
                else:
                    print(f"    No strokes adjustment needed")
            else:
                print(f"    Net score 72 or higher - no adjustment")
    
    print(f"\n--- FINAL RESULTS ---")
    print(f"Total adjustments made: {len(adjustments_log)}")
    for adjustment in adjustments_log:
        print(f"  - {adjustment['name']}: {adjustment['old']} → {adjustment['new']} (adjustment: {adjustment['adjustment']}, reason: {adjustment['reason']})")
    
    conn.commit()
    conn.close()
    print(f"=== HANDICAP ADJUSTMENTS COMPLETE ===\n")
    return adjustments_log

# --- REMOVE: Handicap adjustment log for tournament ---

# --- NEW: Handicap adjustment log for tournament ---
def get_handicap_adjustments_for_tournament(tournament_id):
    conn = get_db_connection()
    adjustments_log = []

    # Get all scores for this tournament with member details - ORDER BY total_score for tie-breaking
    scores = conn.execute('''
        SELECT ts.*, m.name, m.gender, m.id as member_id, m.gross_win, m.handicap, ts.total_score, ts.net_handicap, m.tournaments_played
        FROM tournament_scores ts
        JOIN members m ON ts.member_id = m.id
        WHERE ts.tournament_id = ?
        ORDER BY ts.total_score
    ''', (tournament_id,)).fetchall()

    if not scores:
        conn.close()
        return []

    # Replicate the same logic as apply_handicap_adjustments
    # Gross leaderboard - includes all players (the website logic determines who appears in gross vs net)
    gross_scores = scores  # Include all scores for gross leaderboard
    
    # Separate by gender for gross scores
    gross_male_scores = [score for score in gross_scores if score['gender'] == 'Male']
    gross_female_scores = [score for score in gross_scores if score['gender'] == 'Female']
    
    # Sort gross scores by total_score (gross score) to get actual winners
    gross_male_scores.sort(key=lambda x: x['total_score'] if x['total_score'] is not None else float('inf'))
    gross_female_scores.sort(key=lambda x: x['total_score'] if x['total_score'] is not None else float('inf'))
    
    # Get the winners of gross leaderboards (1st place in each gender)
    # These are the #1 players on the gross leaderboard display
    gross_male_winners = gross_male_scores[:1] if gross_male_scores else []
    gross_female_winners = gross_female_scores[:1] if gross_female_scores else []
    
    # Create list of winner member IDs to exclude from net leaderboards
    # These are the gross champions of THIS tournament who should not get net position adjustments
    this_tournament_gross_winners = [score['member_id'] for score in gross_male_winners + gross_female_winners]
    
    # Net leaderboard excludes gross winners of THIS tournament and members with 3 or fewer tournaments played
    net_scores = [score for score in scores if score['member_id'] not in this_tournament_gross_winners and (score['tournaments_played'] if score['tournaments_played'] is not None else 0) > 3]
    
    # Net leaderboard INCLUDING gross winners (for strokes-under-72 adjustment) - excludes only members with 3 or fewer tournaments played
    # Note: Gross winners of THIS tournament ARE included for strokes adjustments
    net_scores_including_gross = [score for score in scores if (score['tournaments_played'] if score['tournaments_played'] is not None else 0) > 3]
    
    # Separate net scores by gender (excluding gross winners for position adjustments)
    net_male_scores = [score for score in net_scores if score['gender'] == 'Male']
    net_female_scores = [score for score in net_scores if score['gender'] == 'Female']
    
    # Separate net scores INCLUDING gross winners by gender (for strokes-under-72 adjustments)
    net_male_scores_including_gross = [score for score in net_scores_including_gross if score['gender'] == 'Male']
    net_female_scores_including_gross = [score for score in net_scores_including_gross if score['gender'] == 'Female']

    # Process each gender category for traditional NET leaderboard (position adjustments only)
    for gender_scores in [net_male_scores, net_female_scores]:
        if not gender_scores:
            continue
        
        # Create tuples exactly like the template does: (score, net_score)
        calculated_net_scores = []
        for score in gender_scores:
            if score['total_score'] is not None and score['net_handicap'] is not None:
                net_score = int(score['total_score'] - score['net_handicap'])  # Use int() like template
                calculated_net_scores.append((score, net_score))
        
        # Sort by net score (attribute 1 of the tuple) - exactly like template
        # The stable sort preserves the original gross score order for tie-breaking
        calculated_net_scores.sort(key=lambda x: x[1])
        top_3 = calculated_net_scores[:3]
        
        for i, (score, net_score) in enumerate(top_3, 1):
            # Old handicap is the net_handicap at the time of the tournament (original handicap)
            old_handicap = score['net_handicap']
            # New handicap is the current value in the members table
            new_handicap_row = conn.execute(
                'SELECT handicap FROM members WHERE id = ?', (score['member_id'],)
            ).fetchone()
            new_handicap = new_handicap_row['handicap'] if new_handicap_row else None
            adjustment = new_handicap - old_handicap if new_handicap is not None and old_handicap is not None else None
            adjustments_log.append({
                "name": score['name'],
                "old": old_handicap,
                "new": new_handicap,
                "adjustment": adjustment,
                "reason": f"Net {i}{'st' if i == 1 else 'nd' if i == 2 else 'rd'} place"
            })
    
    # Process strokes-under-72 adjustments for net leaderboard INCLUDING gross winners
    all_players_with_adjustments = {}
    for gender_scores in [net_male_scores_including_gross, net_female_scores_including_gross]:
        if not gender_scores:
            continue
        
        # Create tuples for all eligible players: (score, net_score)
        all_calculated_net_scores = []
        for score in gender_scores:
            if score['total_score'] is not None and score['net_handicap'] is not None:
                net_score = int(score['total_score'] - score['net_handicap'])
                all_calculated_net_scores.append((score, net_score))
        
        # Check for strokes-under-72 adjustments
        for score, net_score in all_calculated_net_scores:
            strokes_under_72 = 72 - net_score
            if strokes_under_72 > 0:  # Only apply if net score is under 72
                old_handicap = score['net_handicap']
                strokes_adjustment = calculate_strokes_adjustment(old_handicap, strokes_under_72)
                if strokes_adjustment != 0:  # Only track if there's an actual adjustment
                    player_name = score['name']
                    # Check if this player already has a log entry (from position adjustment)
                    existing_log = next((log for log in adjustments_log if log['name'] == player_name), None)
                    if existing_log:
                        # Update existing log entry to include strokes adjustment
                        new_handicap_row = conn.execute(
                            'SELECT handicap FROM members WHERE id = ?', (score['member_id'],)
                        ).fetchone()
                        new_handicap = new_handicap_row['handicap'] if new_handicap_row else None
                        existing_log['new'] = new_handicap
                        existing_log['adjustment'] = new_handicap - old_handicap  # Total adjustment is the difference
                        existing_log['reason'] = existing_log['reason'] + f" + {strokes_under_72} strokes under 72"
                    else:
                        # Add new log entry for strokes-only adjustment
                        new_handicap_row = conn.execute(
                            'SELECT handicap FROM members WHERE id = ?', (score['member_id'],)
                        ).fetchone()
                        new_handicap = new_handicap_row['handicap'] if new_handicap_row else None
                        adjustments_log.append({
                            "name": player_name,
                            "old": old_handicap,
                            "new": new_handicap,
                            "adjustment": new_handicap - old_handicap,  # Total adjustment is the difference
                            "reason": f"{strokes_under_72} strokes under 72"
                        })
    
    conn.close()
    return adjustments_log
# --- NEW: Handicap adjustment log for tournament ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/members', methods=['GET', 'POST'])
def members():
    if request.method == 'POST':
        # Add new member
        name = request.form['name']
        handicap = float(request.form['handicap'])
        gender = request.form['gender']
        gross_win = 1 if 'gross_win' in request.form else 0
        points = int(request.form.get('points', 0))
        
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO members (name, handicap, gender, gross_win, points) VALUES (?, ?, ?, ?, ?)',
            (name, handicap, gender, gross_win, points)
        )
        conn.commit()
        conn.close()
        flash('Member added successfully.', 'success')
        return redirect(url_for('members'))
    
    # List members
    conn = get_db_connection()
    members = conn.execute('SELECT * FROM members ORDER BY id').fetchall()
    conn.close()
    return render_template('members.html', members=members)

@app.route('/tournaments', methods=['GET', 'POST'])
def tournaments():
    if request.method == 'POST':
        # Add new tournament
        name = request.form['name']
        date = request.form['date']
        description = request.form.get('description', '')
        
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO tournaments (name, date, description) VALUES (?, ?, ?)',
            (name, date, description)
        )
        conn.commit()
        conn.close()
        flash('Tournament created successfully.', 'success')
        return redirect(url_for('tournaments'))
    
    # List all tournaments
    conn = get_db_connection()
    tournaments = conn.execute('SELECT * FROM tournaments ORDER BY date DESC').fetchall()
    conn.close()
    return render_template('tournaments.html', tournaments=tournaments)

@app.route('/tournament/<int:tournament_id>')
def view_tournament(tournament_id):
    conn = get_db_connection()
    selected_group_id = request.args.get('group_id', type=int)
    
    # Get tournament info
    tournament = conn.execute(
        'SELECT * FROM tournaments WHERE id = ?', 
        (tournament_id,)
    ).fetchone()
    
    if tournament is None:
        conn.close()
        return redirect(url_for('tournaments'))
    
    # Get all groups for this tournament and their members
    groups_query = conn.execute(
        'SELECT * FROM groups WHERE tournament_id = ? ORDER BY name',
        (tournament_id,)
    ).fetchall()
    
    groups = []
    for group_row in groups_query:
        group = dict(group_row)
        members_in_group = conn.execute('''
            SELECT m.name FROM members m
            JOIN group_members gm ON m.id = gm.member_id
            WHERE gm.group_id = ?
            ORDER BY m.name
        ''', (group['id'],)).fetchall()
        group['members'] = [member['name'] for member in members_in_group]
        groups.append(group)
    
    # Get tournament scores with member details and all hole scores
    if selected_group_id:
        all_scores = conn.execute('''
            SELECT ts.*, m.name, m.handicap AS old_handicap, ts.net_handicap AS handicap, m.gross_win, m.gender, m.tournaments_played
            FROM tournament_scores ts
            JOIN members m ON ts.member_id = m.id
            JOIN group_members gm ON m.id = gm.member_id
            WHERE ts.tournament_id = ? AND gm.group_id = ?
            ORDER BY ts.total_score
        ''', (tournament_id, selected_group_id)).fetchall()
        
        # Get members in the selected group for adding new scores
        members = conn.execute('''
            SELECT m.*
            FROM members m
            JOIN group_members gm ON m.id = gm.member_id
            WHERE gm.group_id = ?
            ORDER BY m.name
        ''', (selected_group_id,)).fetchall()
    else:
        all_scores = conn.execute('''
            SELECT ts.*, m.name, m.handicap AS old_handicap, ts.net_handicap AS handicap, m.gross_win, m.gender, m.tournaments_played
            FROM tournament_scores ts
            JOIN members m ON ts.member_id = m.id
            WHERE ts.tournament_id = ?
            ORDER BY ts.total_score
        ''', (tournament_id,)).fetchall()
        
        # Get all members for adding new scores
        members = conn.execute('SELECT * FROM members ORDER BY name').fetchall()
    
    # Separate scores for different leaderboards
    # For finalized tournaments, show gross leaderboard as it was during tournament
    # For non-finalized tournaments, exclude members with existing gross_win = 1
    if tournament['finalized']:
        # For finalized tournaments, we need to reconstruct the gross leaderboard as it was
        # during the tournament by excluding members who had gross_win=1 BEFORE this tournament
        # We'll identify the winners from this tournament and include them in the gross leaderboard
        
        # Get all scores for this tournament first
        all_scores_for_gross = list(all_scores)
        
        # Identify who won gross in THIS tournament by finding top performers who now have gross_win=1
        # but should still appear in the gross leaderboard for this tournament
        gross_male_candidates = [score for score in all_scores_for_gross if score['gender'] == 'Male']
        gross_female_candidates = [score for score in all_scores_for_gross if score['gender'] == 'Female']
        
        # Sort by total score to find the winners
        gross_male_candidates.sort(key=lambda x: x['total_score'] if x['total_score'] is not None else float('inf'))
        gross_female_candidates.sort(key=lambda x: x['total_score'] if x['total_score'] is not None else float('inf'))
        
        # The winner of each gender in this tournament should be included in gross leaderboard
        # even if they now have gross_win=1 (because they won it in THIS tournament)
        current_tournament_gross_winners = set()
        if gross_male_candidates:
            current_tournament_gross_winners.add(gross_male_candidates[0]['member_id'])
        if gross_female_candidates:
            current_tournament_gross_winners.add(gross_female_candidates[0]['member_id'])
        
        # For finalized tournaments, exclude members with gross_win=1 UNLESS they won it in this tournament
        gross_scores = [score for score in all_scores if (not score['gross_win'] or score['member_id'] in current_tournament_gross_winners)]
    else:
        # For non-finalized tournaments, exclude members with existing gross_win = 1
        gross_scores = [score for score in all_scores if not score['gross_win']]
    
    # Separate by gender for gross scores
    gross_male_scores = [score for score in gross_scores if score['gender'] == 'Male']
    gross_female_scores = [score for score in gross_scores if score['gender'] == 'Female']
    
    # Get the winners of gross leaderboards (1st place in each gender)
    gross_male_winners = gross_male_scores[:1] if gross_male_scores else []
    gross_female_winners = gross_female_scores[:1] if gross_female_scores else []
    
    # Create list of winner member IDs to exclude from net leaderboards
    gross_winners = [score['member_id'] for score in gross_male_winners + gross_female_winners]
    
    # Net leaderboard excludes gross winners and members with 3 or fewer tournaments played
    net_scores = [score for score in all_scores if score['member_id'] not in gross_winners and (score['tournaments_played'] if score['tournaments_played'] is not None else 0) > 3]
    
    # Separate net scores by gender
    net_male_scores = [score for score in net_scores if score['gender'] == 'Male']
    net_female_scores = [score for score in net_scores if score['gender'] == 'Female']
    
    # --- NEW: Handicap adjustments log ---
    adjustments_log = []
    if tournament['finalized']:
        adjustments_log = get_handicap_adjustments_for_tournament(tournament_id)
    
    # Define default honor types and ensure they exist for the tournament
    default_honor_types = ['Long Drive', 'KP 1', 'KP 2', 'KP 3', 'KP 4', 'KP 5', 'KP 6', 'Eagle']
    for i, honor_type_key in enumerate(default_honor_types):
        exists = conn.execute(
            'SELECT id FROM tournament_honor_types WHERE tournament_id = ? AND original_honor_type = ?',
            (tournament_id, honor_type_key)
        ).fetchone()
        if not exists:
            conn.execute(
                'INSERT INTO tournament_honor_types (tournament_id, original_honor_type, custom_name, display_order) VALUES (?, ?, ?, ?)',
                (tournament_id, honor_type_key, honor_type_key, i)
            )
    conn.commit()

    # Get all customizable honor types for this tournament
    honor_types = conn.execute(
        'SELECT * FROM tournament_honor_types WHERE tournament_id = ? ORDER BY display_order', (tournament_id,)
    ).fetchall()

    # Get awarded honorable mentions
    honorable_mentions = conn.execute('''
        SELECT hm.honor_type, m.name as member_name, hm.balls_awarded
        FROM honorable_mentions hm
        JOIN members m ON hm.member_id = m.id
        WHERE hm.tournament_id = ?
    ''', (tournament_id,)).fetchall()
    
    # Create a dictionary for easy template access
    honors_dict = {mention['honor_type']: mention['member_name'] for mention in honorable_mentions}
    honors_balls = {mention['honor_type']: (mention['balls_awarded'] if mention['balls_awarded'] is not None else 0) for mention in honorable_mentions}
    
    # Calculate automatic awards from leaderboards
    automatic_awards = {}
    
    # Gross 1st place awards (Male and Female)
    if gross_male_scores:
        automatic_awards['Gross 1st Male'] = gross_male_scores[0]['name']
    if gross_female_scores:
        automatic_awards['Gross 1st Female'] = gross_female_scores[0]['name']
    
    # Net leaderboard awards (combined male and female, sorted by net score)
    all_net_scores = net_male_scores + net_female_scores
    if all_net_scores:
        # Calculate net scores and sort
        calculated_net_scores = []
        for score in all_net_scores:
            if score['total_score'] is not None and score['handicap'] is not None:
                net_score = int(score['total_score'] - score['handicap'])
                calculated_net_scores.append((score, net_score))
        
        # Sort by net score
        calculated_net_scores.sort(key=lambda x: x[1])
        
        # Award positions
        positions = ['1st', '2nd', '3rd', '4th', '5th']
        for i, position in enumerate(positions):
            if i < len(calculated_net_scores):
                automatic_awards[f'Net {position}'] = calculated_net_scores[i][0]['name']
        
        # Lucky 7 (7th place)
        if len(calculated_net_scores) >= 7:
            automatic_awards['Lucky 7'] = calculated_net_scores[6][0]['name']
        
        # BB (second last place)
        if len(calculated_net_scores) >= 2:
            automatic_awards['BB'] = calculated_net_scores[-2][0]['name']
    
    conn.close()
    return render_template('view_tournament.html', tournament=tournament, gross_male_scores=gross_male_scores, gross_female_scores=gross_female_scores, net_male_scores=net_male_scores, net_female_scores=net_female_scores, members=members, groups=groups, selected_group_id=selected_group_id, adjustments_log=adjustments_log, honors_dict=honors_dict, honor_types=honor_types, automatic_awards=automatic_awards, honors_balls=honors_balls)

@app.route('/tournament/<int:tournament_id>/add_score', methods=['POST'])
def add_tournament_score(tournament_id):
    member_id = int(request.form['member_id'])
    
    # Get all hole scores
    hole_scores = []
    for i in range(1, 19):
        hole_score = int(request.form[f'hole{i}'])
        hole_scores.append(hole_score)
    
    # Calculate total score
    total_score = sum(hole_scores)
    
    conn = get_db_connection()
    member_handicap = conn.execute('SELECT handicap FROM members WHERE id = ?', (member_id,)).fetchone()['handicap']

    conn.execute('''
        INSERT INTO tournament_scores (
            tournament_id, member_id, 
            hole1, hole2, hole3, hole4, hole5, hole6, hole7, hole8, hole9,
            hole10, hole11, hole12, hole13, hole14, hole15, hole16, hole17, hole18,
            total_score, net_handicap
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', [tournament_id, member_id] + hole_scores + [total_score, member_handicap])
    
    # Increment tournaments_played for this member
    conn.execute('UPDATE members SET tournaments_played = tournaments_played + 1 WHERE id = ?', (member_id,))
    conn.commit()
    conn.close()
    
    flash('Score added successfully.', 'success')
    return redirect(url_for('view_tournament', tournament_id=tournament_id))

@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Update member
        new_id = int(request.form['id'])
        name = request.form['name']
        handicap = float(request.form['handicap'])
        gender = request.form['gender']
        gross_win = 1 if 'gross_win' in request.form else 0
        tournaments_played = int(request.form['tournaments_played'])
        points = int(request.form.get('points', 0))
        # Check if the new ID already exists (if it's different from current)
        if new_id != member_id:
            existing = conn.execute('SELECT id FROM members WHERE id = ?', (new_id,)).fetchone()
            if existing:
                conn.close()
                flash('Error: Member ID already exists', 'error')
                return redirect(url_for('members'))
        # Update member with new ID
        conn.execute(
            'UPDATE members SET id = ?, name = ?, handicap = ?, gender = ?, gross_win = ?, tournaments_played = ?, points = ? WHERE id = ?',
            (new_id, name, handicap, gender, gross_win, tournaments_played, points, member_id)
        )
        
        # Update all tournament scores that reference this member
        conn.execute(
            'UPDATE tournament_scores SET member_id = ? WHERE member_id = ?',
            (new_id, member_id)
        )
        
        # Update all group_members that reference this member
        conn.execute(
            'UPDATE group_members SET member_id = ? WHERE member_id = ?',
            (new_id, member_id)
        )
        
        conn.commit()
        conn.close()
        flash('Member updated successfully.', 'success')
        return redirect(url_for('members'))
    
    # Get member data for the form
    member = conn.execute('SELECT * FROM members WHERE id = ?', (member_id,)).fetchone()
    conn.close()
    
    if member is None:
        return redirect(url_for('members'))
    
    return render_template('edit_member.html', member=member)

@app.route('/delete_member/<int:member_id>', methods=['GET'])
def delete_member(member_id):
    conn = get_db_connection()
    # Delete associated tournament scores first
    conn.execute('DELETE FROM tournament_scores WHERE member_id = ?', (member_id,))
    # Delete the member
    conn.execute('DELETE FROM members WHERE id = ?', (member_id,))
    conn.commit()
    conn.close()
    
    # Reset auto-increment if this was the last member
    reset_members_autoincrement()
    
    flash('Member deleted.', 'success')
    return redirect(url_for('members'))

@app.route('/member/<int:member_id>/set_points', methods=['POST'])
def set_member_points(member_id):
    try:
        points = int(request.form.get('points', 0))
        if points < 0:
            points = 0
    except (TypeError, ValueError):
        points = 0

    conn = get_db_connection()
    conn.execute('UPDATE members SET points = ? WHERE id = ?', (points, member_id))
    conn.commit()
    conn.close()
    flash('Points updated.', 'success')
    return redirect(url_for('members'))

@app.route('/edit_tournament/<int:tournament_id>', methods=['GET', 'POST'])
def edit_tournament(tournament_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Update tournament
        name = request.form['name']
        date = request.form['date']
        description = request.form.get('description', '')
        
        conn.execute(
            'UPDATE tournaments SET name = ?, date = ?, description = ? WHERE id = ?',
            (name, date, description, tournament_id)
        )
        conn.commit()
        conn.close()
        flash('Tournament updated successfully.', 'success')
        return redirect(url_for('tournaments'))
    
    # Get tournament data for the form
    tournament = conn.execute(
        'SELECT * FROM tournaments WHERE id = ?', 
        (tournament_id,)
    ).fetchone()
    conn.close()
    
    if tournament is None:
        return redirect(url_for('tournaments'))
    
    return render_template('edit_tournament.html', tournament=tournament)

@app.route('/finalize_tournament/<int:tournament_id>', methods=['GET'])
def finalize_tournament(tournament_id):
    print(f"\n=== FINALIZING TOURNAMENT {tournament_id} ===")
    conn = get_db_connection()
    # Check if tournament exists
    tournament = conn.execute(
        'SELECT * FROM tournaments WHERE id = ?', 
        (tournament_id,)
    ).fetchone()
    if tournament is None:
        print(f"Tournament {tournament_id} not found")
        conn.close()
        return redirect(url_for('tournaments'))
    
    print(f"Finalizing tournament: {tournament['name']}")
    
    # Get all tournament scores to identify gross winners
    all_scores = conn.execute('''
        SELECT ts.*, m.name, m.handicap AS old_handicap, ts.net_handicap AS handicap, m.gross_win, m.gender, m.tournaments_played
        FROM tournament_scores ts
        JOIN members m ON ts.member_id = m.id
        WHERE ts.tournament_id = ?
        ORDER BY ts.total_score
    ''', (tournament_id,)).fetchall()
    
    print(f"Found {len(all_scores)} scores for tournament")
    
    # Get gross leaderboard (excludes members with existing gross_win = 1)
    gross_scores = [score for score in all_scores if not score['gross_win']]
    print(f"Gross scores (excluding existing gross_win=1): {len(gross_scores)}")
    
    # Separate by gender for gross scores
    gross_male_scores = [score for score in gross_scores if score['gender'] == 'Male']
    gross_female_scores = [score for score in gross_scores if score['gender'] == 'Female']
    
    # Get the winners of gross leaderboards (1st place in each gender)
    gross_male_winners = gross_male_scores[:1] if gross_male_scores else []
    gross_female_winners = gross_female_scores[:1] if gross_female_scores else []
    
    print(f"Gross male winners: {[w['name'] for w in gross_male_winners]}")
    print(f"Gross female winners: {[w['name'] for w in gross_female_winners]}")
    
    # Mark the gross winners with gross_win = 1
    for winner in gross_male_winners + gross_female_winners:
        print(f"Marking {winner['name']} as gross winner")
        conn.execute(
            'UPDATE members SET gross_win = 1 WHERE id = ?',
            (winner['member_id'],)
        )
    
    # Mark tournament as finalized
    conn.execute(
        'UPDATE tournaments SET finalized = 1 WHERE id = ?',
        (tournament_id,)
    )
    conn.commit()
    conn.close()
    
    print("Tournament finalized, applying handicap adjustments...")
    # Apply handicap adjustments
    apply_handicap_adjustments(tournament_id)
    print("Handicap adjustments completed")
    
    # Redirect to the view_tournament page
    flash('Tournament finalized and handicaps adjusted.', 'success')
    return redirect(url_for('view_tournament', tournament_id=tournament_id))

@app.route('/delete_tournament/<int:tournament_id>', methods=['GET'])
def delete_tournament(tournament_id):
    conn = get_db_connection()
    # Delete all scores for this tournament first
    conn.execute('DELETE FROM tournament_scores WHERE tournament_id = ?', (tournament_id,))
    # Delete the tournament
    conn.execute('DELETE FROM tournaments WHERE id = ?', (tournament_id,))
    conn.commit()
    conn.close()
    flash('Tournament deleted.', 'success')
    return redirect(url_for('tournaments'))

@app.route('/edit_score/<int:score_id>', methods=['GET', 'POST'])
def edit_score(score_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Update score
        member_id = int(request.form['member_id'])
        
        # Get all hole scores
        hole_scores = []
        for i in range(1, 19):
            hole_score = int(request.form[f'hole{i}'])
            hole_scores.append(hole_score)
        
        # Calculate total score
        total_score = sum(hole_scores)
        
        conn.execute('''
            UPDATE tournament_scores SET 
                member_id = ?, 
                hole1 = ?, hole2 = ?, hole3 = ?, hole4 = ?, hole5 = ?, hole6 = ?, hole7 = ?, hole8 = ?, hole9 = ?,
                hole10 = ?, hole11 = ?, hole12 = ?, hole13 = ?, hole14 = ?, hole15 = ?, hole16 = ?, hole17 = ?, hole18 = ?,
                total_score = ?
            WHERE id = ?
        ''', [member_id] + hole_scores + [total_score, score_id])
        
        conn.commit()
        
        # Get tournament_id for redirect
        tournament_id = conn.execute(
            'SELECT tournament_id FROM tournament_scores WHERE id = ?',
            (score_id,)
        ).fetchone()['tournament_id']
        
        conn.close()
        flash('Score updated successfully.', 'success')
        return redirect(url_for('view_tournament', tournament_id=tournament_id))
    
    # Get score data for the form
    score_data = conn.execute(
        'SELECT * FROM tournament_scores WHERE id = ?', 
        (score_id,)
    ).fetchone()
    
    if score_data is None:
        conn.close()
        return redirect(url_for('tournaments'))
    
    members = conn.execute('SELECT * FROM members ORDER BY name').fetchall()
    conn.close()
    
    return render_template('edit_score.html', score=score_data, members=members)

@app.route('/delete_score/<int:score_id>', methods=['GET'])
def delete_score(score_id):
    conn = get_db_connection()
    
    # Get tournament_id before deleting
    tournament_id = conn.execute(
        'SELECT tournament_id FROM tournament_scores WHERE id = ?',
        (score_id,)
    ).fetchone()['tournament_id']
    
    # Delete the score
    conn.execute('DELETE FROM tournament_scores WHERE id = ?', (score_id,))
    conn.commit()
    conn.close()
    
    flash('Score deleted.', 'success')
    return redirect(url_for('view_tournament', tournament_id=tournament_id))

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

@app.route('/tournament/<int:tournament_id>/groups')
def manage_groups(tournament_id):
    conn = get_db_connection()
    
    # Get tournament info
    tournament = conn.execute(
        'SELECT * FROM tournaments WHERE id = ?', 
        (tournament_id,)
    ).fetchone()
    
    if tournament is None:
        conn.close()
        return redirect(url_for('tournaments'))
    
    # Get all groups for this tournament
    groups_query = conn.execute('''
        SELECT g.* FROM groups g WHERE g.tournament_id = ?
    ''', (tournament_id,)).fetchall()

    # Convert to list of dicts and fetch members for each group
    groups = []
    for row in groups_query:
        group = dict(row)
        if group.get('tee_time'):
            try:
                group['tee_time'] = datetime.strptime(group['tee_time'], '%H:%M').time()
            except (ValueError, TypeError):
                group['tee_time'] = None
        
        # Get members for this group
        members_query = conn.execute('''
            SELECT m.name 
            FROM members m
            JOIN group_members gm ON m.id = gm.member_id
            WHERE gm.group_id = ?
            ORDER BY m.name
        ''', (group['id'],)).fetchall()
        group['members'] = [member['name'] for member in members_query]
        
        groups.append(group)
        
    groups.sort(key=lambda x: natural_sort_key(x['name']))
    
    # Get all members (still needed for adding members to groups on other pages, maybe not here)
    all_members = conn.execute('SELECT * FROM members ORDER BY name').fetchall()
    
    conn.close()
    return render_template('manage_groups.html', tournament=tournament, groups=groups, all_members=all_members)

@app.route('/tournament/<int:tournament_id>/groups/add', methods=['POST'])
def add_group(tournament_id):
    group_name = request.form['group_name']
    
    # Generate a unique secure token for the group
    secure_token = str(uuid.uuid4())
    
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO groups (tournament_id, name, secure_token) VALUES (?, ?, ?)',
        (tournament_id, group_name, secure_token)
    )
    conn.commit()
    conn.close()
    
    flash('Group added.', 'success')
    return redirect(url_for('manage_groups', tournament_id=tournament_id))


@app.route('/tournament/<int:tournament_id>/groups/set_staggered_tee_times', methods=['POST'])
def set_staggered_tee_times(tournament_id):
    start_time_str = request.form.get('start_time')
    stagger_minutes = int(request.form.get('stagger_minutes', 10))
    
    start_time = datetime.strptime(start_time_str, '%H:%M')
    
    conn = get_db_connection()
    
    groups_query = conn.execute(
        'SELECT id, name FROM groups WHERE tournament_id = ?',
        (tournament_id,)
    ).fetchall()
    
    groups = [dict(row) for row in groups_query]
    groups.sort(key=lambda x: natural_sort_key(x['name']))
    
    current_tee_time = start_time
    for group in groups:
        conn.execute(
            'UPDATE groups SET tee_time = ? WHERE id = ?',
            (current_tee_time.strftime('%H:%M'), group['id'])
        )
        current_tee_time += timedelta(minutes=stagger_minutes)
        
    conn.commit()
    conn.close()
    
    flash('Staggered tee times set.', 'success')
    return redirect(url_for('manage_groups', tournament_id=tournament_id))

@app.route('/group/<int:group_id>')
def view_group(group_id):
    conn = get_db_connection()
    
    # Get group info with tournament details
    group = conn.execute('''
        SELECT g.*, t.name as tournament_name, t.id as tournament_id
        FROM groups g
        JOIN tournaments t ON g.tournament_id = t.id
        WHERE g.id = ?
    ''', (group_id,)).fetchone()
    
    if group is None:
        conn.close()
        return redirect(url_for('tournaments'))
    
    # Get members in this group
    group_members = conn.execute('''
        SELECT m.*, gm.id as group_member_id
        FROM members m
        JOIN group_members gm ON m.id = gm.member_id
        WHERE gm.group_id = ?
        ORDER BY m.name
    ''', (group_id,)).fetchall()
    
    # Get members not in ANY group for this tournament (including current group)
    available_members = conn.execute('''
        SELECT m.*
        FROM members m
        WHERE m.id NOT IN (
            SELECT gm.member_id 
            FROM group_members gm 
            WHERE gm.tournament_id = ?
        )
        ORDER BY m.name
    ''', (group['tournament_id'],)).fetchall()
    
    # Also get members from other groups in this tournament (for moving between groups)
    other_group_members = conn.execute('''
        SELECT m.*, g.name as current_group_name, gm.id as group_member_id
        FROM members m
        JOIN group_members gm ON m.id = gm.member_id
        JOIN groups g ON gm.group_id = g.id
        WHERE gm.tournament_id = ? AND gm.group_id != ?
        ORDER BY m.name
    ''', (group['tournament_id'], group_id)).fetchall()
    
    conn.close()
    return render_template('view_group.html', group=group, group_members=group_members, available_members=available_members, other_group_members=other_group_members)

@app.route('/group/<int:group_id>/add_member', methods=['POST'])
def add_member_to_group(group_id):
    member_id = int(request.form['member_id'])
    
    conn = get_db_connection()
    
    # Get tournament_id for this group
    tournament_id = conn.execute(
        'SELECT tournament_id FROM groups WHERE id = ?',
        (group_id,)
    ).fetchone()['tournament_id']
    
    try:
        # Check if member is already in another group for this tournament
        existing = conn.execute(
            'SELECT group_id FROM group_members WHERE member_id = ? AND tournament_id = ?',
            (member_id, tournament_id)
        ).fetchone()
        
        if existing:
            # Remove from existing group first
            conn.execute(
                'DELETE FROM group_members WHERE member_id = ? AND tournament_id = ?',
                (member_id, tournament_id)
            )
        
        # Add to new group
        conn.execute(
            'INSERT INTO group_members (group_id, member_id, tournament_id) VALUES (?, ?, ?)',
            (group_id, member_id, tournament_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()
    
    flash('Member added to group.', 'success')
    return redirect(url_for('view_group', group_id=group_id))

@app.route('/group_member/<int:group_member_id>/remove', methods=['POST'])
def remove_member_from_group(group_member_id):
    conn = get_db_connection()
    
    # Get group_id before deleting
    group_id = conn.execute(
        'SELECT group_id FROM group_members WHERE id = ?',
        (group_member_id,)
    ).fetchone()['group_id']
    
    conn.execute('DELETE FROM group_members WHERE id = ?', (group_member_id,))
    conn.commit()
    conn.close()
    
    flash('Member removed from group.', 'success')
    return redirect(url_for('view_group', group_id=group_id))

@app.route('/delete_group/<int:group_id>', methods=['POST'])
def delete_group(group_id):
    conn = get_db_connection()
    
    # Get tournament_id before deleting
    tournament_id = conn.execute(
        'SELECT tournament_id FROM groups WHERE id = ?',
        (group_id,)
    ).fetchone()['tournament_id']
    
    # Delete group members first
    conn.execute('DELETE FROM group_members WHERE group_id = ?', (group_id,))
    # Delete the group
    conn.execute('DELETE FROM groups WHERE id = ?', (group_id,))
    conn.commit()
    conn.close()
    
    flash('Group deleted.', 'success')
    return redirect(url_for('manage_groups', tournament_id=tournament_id))

@app.route('/group/<int:group_id>/enter_scores')
def group_score_entry(group_id):
    """Group-specific score entry page - allows only group members to enter scores"""
    conn = get_db_connection()
    
    # Get group info with tournament details
    group = conn.execute('''
        SELECT g.*, t.name as tournament_name, t.id as tournament_id, t.finalized
        FROM groups g
        JOIN tournaments t ON g.tournament_id = t.id
        WHERE g.id = ?
    ''', (group_id,)).fetchone()
    
    if group is None:
        conn.close()
        return redirect(url_for('tournaments'))
    
    # Check if tournament is finalized
    if group['finalized']:
        conn.close()
        flash('This tournament has been finalized. No new scores can be added.', 'error')
        return redirect(url_for('view_group', group_id=group_id))
    
    # Get members in this group who don't already have scores
    group_members = conn.execute('''
        SELECT m.*, ts.id as has_score
        FROM members m
        JOIN group_members gm ON m.id = gm.member_id
        LEFT JOIN tournament_scores ts ON m.id = ts.member_id AND ts.tournament_id = ?
        WHERE gm.group_id = ?
        ORDER BY m.name
    ''', (group['tournament_id'], group_id)).fetchall()
    
    # Get existing scores for this group in this tournament
    existing_scores = conn.execute('''
        SELECT ts.*, m.name, m.handicap AS old_handicap, ts.net_handicap AS handicap, m.gross_win, m.gender
        FROM tournament_scores ts
        JOIN members m ON ts.member_id = m.id
        JOIN group_members gm ON m.id = gm.member_id
        WHERE ts.tournament_id = ? AND gm.group_id = ?
        ORDER BY ts.total_score
    ''', (group['tournament_id'], group_id)).fetchall()
    
    conn.close()
    return render_template('group_score_entry.html', 
                         group=group, 
                         group_members=group_members, 
                         existing_scores=existing_scores)

@app.route('/group/<int:group_id>/add_score', methods=['POST'])
def add_group_score(group_id):
    """Add score for a group member - restricted to group members only"""
    conn = get_db_connection()
    
    # Get group info to verify tournament
    group = conn.execute('''
        SELECT g.*, t.finalized
        FROM groups g
        JOIN tournaments t ON g.tournament_id = t.id
        WHERE g.id = ?
    ''', (group_id,)).fetchone()
    
    if group is None or group['finalized']:
        conn.close()
        flash('Invalid group or tournament is finalized.', 'error')
        return redirect(url_for('view_group', group_id=group_id))
    
    member_id = int(request.form['member_id'])
    tournament_id = group['tournament_id']
    
    # Verify that the member is actually in this group
    member_in_group = conn.execute(
        'SELECT 1 FROM group_members WHERE group_id = ? AND member_id = ?',
        (group_id, member_id)
    ).fetchone()
    
    if not member_in_group:
        conn.close()
        flash('Member is not in this group.', 'error')
        return redirect(url_for('view_group', group_id=group_id))
    
    # Check if member already has a score for this tournament
    existing_score = conn.execute(
        'SELECT 1 FROM tournament_scores WHERE tournament_id = ? AND member_id = ?',
        (tournament_id, member_id)
    ).fetchone()
    
    if existing_score:
        conn.close()
        flash('This member already has a score for this tournament.', 'error')
        return redirect(url_for('view_group', group_id=group_id))
    
    # Get all hole scores
    hole_scores = []
    for i in range(1, 19):
        hole_score = int(request.form[f'hole{i}'])
        hole_scores.append(hole_score)
    
    # Calculate total score
    total_score = sum(hole_scores)
    
    # Get member's current handicap
    member_handicap = conn.execute('SELECT handicap FROM members WHERE id = ?', (member_id,)).fetchone()['handicap']

    conn.execute('''
        INSERT INTO tournament_scores (
            tournament_id, member_id, 
            hole1, hole2, hole3, hole4, hole5, hole6, hole7, hole8, hole9,
            hole10, hole11, hole12, hole13, hole14, hole15, hole16, hole17, hole18,
            total_score, net_handicap
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', [tournament_id, member_id] + hole_scores + [total_score, member_handicap])
    
    # Increment tournaments_played for this member
    conn.execute('UPDATE members SET tournaments_played = tournaments_played + 1 WHERE id = ?', (member_id,))
    conn.commit()
    conn.close()
    
    flash('Score added for group member.', 'success')
    return redirect(url_for('group_score_entry', group_id=group_id))

@app.route('/tournament/<int:tournament_id>/add_honor', methods=['POST'])
def add_honorable_mention(tournament_id):
    honor_type = request.form['honor_type']
    member_id = int(request.form['member_id'])
    honor_type_name = request.form.get('honor_type_name')

    conn = get_db_connection()
    
    try:
        # Use INSERT OR REPLACE to handle updates
        conn.execute(
            'INSERT OR REPLACE INTO honorable_mentions (tournament_id, member_id, honor_type, honor_type_name) VALUES (?, ?, ?, ?)',
            (tournament_id, member_id, honor_type, honor_type_name)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()
    
    flash('Honorable mention saved.', 'success')
    return redirect(url_for('view_tournament', tournament_id=tournament_id))

@app.route('/tournament/<int:tournament_id>/remove_honor', methods=['POST'])
def remove_honorable_mention(tournament_id):
    honor_type = request.form['honor_type']

    conn = get_db_connection()
    try:
        conn.execute(
            'DELETE FROM honorable_mentions WHERE tournament_id = ? AND honor_type = ?',
            (tournament_id, honor_type)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

    flash('Honorable mention removed.', 'success')
    return redirect(url_for('view_tournament', tournament_id=tournament_id))

@app.route('/tournament/<int:tournament_id>/set_honor_balls', methods=['POST'])
def set_honor_balls(tournament_id):
    honor_type = request.form['honor_type']
    try:
        balls = int(request.form.get('balls', 0))
        if balls < 0:
            balls = 0
    except (TypeError, ValueError):
        balls = 0

    conn = get_db_connection()
    try:
        conn.execute(
            'UPDATE honorable_mentions SET balls_awarded = ? WHERE tournament_id = ? AND honor_type = ?',
            (balls, tournament_id, honor_type)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

    # For fetch-based inline update, return JSON-ish response
    # We won't import jsonify at top just for this; a minimal response is fine
    return ('OK', 200)

@app.route('/tournament/<int:tournament_id>/edit_honor_title', methods=['POST'])
def edit_honor_title(tournament_id):
    honor_type_id = request.form['honor_type_id']
    custom_name = request.form['custom_name']

    conn = get_db_connection()
    try:
        conn.execute(
            'UPDATE tournament_honor_types SET custom_name = ? WHERE id = ? AND tournament_id = ?',
            (custom_name, honor_type_id, tournament_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

    flash('Honor title updated.', 'success')
    return redirect(url_for('view_tournament', tournament_id=tournament_id))

# NEW: Token-based secure score entry routes
@app.route('/score/<token>')
def secure_group_score_entry(token):
    """Secure group-specific score entry page using token authentication"""
    conn = get_db_connection()
    
    # Get group info with tournament details by token
    group = conn.execute('''
        SELECT g.*, t.name as tournament_name, t.id as tournament_id, t.finalized
        FROM groups g
        JOIN tournaments t ON g.tournament_id = t.id
        WHERE g.secure_token = ?
    ''', (token,)).fetchone()
    
    if group is None:
        conn.close()
        flash('Invalid or expired link.', 'error')
        return redirect(url_for('tournaments'))
    
    # Check if tournament is finalized
    if group['finalized']:
        conn.close()
        flash('This tournament has been finalized. No new scores can be added.', 'error')
        return redirect(url_for('tournaments'))
    
    # Get members in this group who don't already have scores
    group_members = conn.execute('''
        SELECT m.*, ts.id as has_score
        FROM members m
        JOIN group_members gm ON m.id = gm.member_id
        LEFT JOIN tournament_scores ts ON m.id = ts.member_id AND ts.tournament_id = ?
        WHERE gm.group_id = ?
        ORDER BY m.name
    ''', (group['tournament_id'], group['id'])).fetchall()
    
    # Get existing scores for this group in this tournament
    existing_scores = conn.execute('''
        SELECT ts.*, m.name, m.handicap AS old_handicap, ts.net_handicap AS handicap, m.gross_win, m.gender
        FROM tournament_scores ts
        JOIN members m ON ts.member_id = m.id
        JOIN group_members gm ON m.id = gm.member_id
        WHERE ts.tournament_id = ? AND gm.group_id = ?
        ORDER BY ts.total_score
    ''', (group['tournament_id'], group['id'])).fetchall()
    
    # Check if any scores have been entered for this group. If not, redirect to hole 1.
    if not existing_scores:
        return redirect(url_for('secure_group_score_entry_by_hole', token=token, hole_number=1))

    conn.close()
    return render_template('secure_group_score_entry.html', 
                         group=group, 
                         group_members=group_members, 
                         existing_scores=existing_scores,
                         token=token,
                         hide_nav=True)

@app.route('/score/<token>/hole/<int:hole_number>', methods=['GET', 'POST'])
def secure_group_score_entry_by_hole(token, hole_number):
    """Secure group-specific score entry page for a single hole."""
    conn = get_db_connection()

    group = conn.execute('''
        SELECT g.*, t.name as tournament_name, t.id as tournament_id, t.finalized
        FROM groups g
        JOIN tournaments t ON g.tournament_id = t.id
        WHERE g.secure_token = ?
    ''', (token,)).fetchone()

    if group is None:
        conn.close()
        flash('Invalid or expired link.', 'error')
        return redirect(url_for('tournaments'))

    if group['finalized']:
        conn.close()
        flash('This tournament has been finalized.', 'error')
        return redirect(url_for('tournaments'))

    group_members = conn.execute('''
        SELECT m.*
        FROM members m
        JOIN group_members gm ON m.id = gm.member_id
        WHERE gm.group_id = ?
        ORDER BY m.name
    ''', (group['id'],)).fetchall()

    if request.method == 'POST':
        action = request.form.get('action')
        scores = request.form.getlist('scores')
        member_ids = request.form.getlist('member_ids')

        for member_id, score in zip(member_ids, scores):
            if score:  # Only process if a score was entered
                score_id = conn.execute(
                    'SELECT id FROM tournament_scores WHERE tournament_id = ? AND member_id = ?',
                    (group['tournament_id'], member_id)
                ).fetchone()

                if score_id:
                    conn.execute(
                        f'UPDATE tournament_scores SET hole{hole_number} = ? WHERE id = ?',
                        (score, score_id['id'])
                    )
                else:
                    member_handicap = conn.execute('SELECT handicap FROM members WHERE id = ?', (member_id,)).fetchone()['handicap']
                    conn.execute(
                        f'INSERT INTO tournament_scores (tournament_id, member_id, hole{hole_number}, net_handicap) VALUES (?, ?, ?, ?)',
                        (group['tournament_id'], member_id, score, member_handicap)
                    )
        
        for member_id in member_ids:
            sum_expression = ' + '.join([f'COALESCE(hole{i}, 0)' for i in range(1, 19)])
            total_score_query = f'SELECT {sum_expression} FROM tournament_scores WHERE tournament_id = ? AND member_id = ?'
            total_score_result = conn.execute(total_score_query, (group['tournament_id'], member_id)).fetchone()
            total_score = total_score_result[0] if total_score_result else 0
            
            conn.execute(
                'UPDATE tournament_scores SET total_score = ? WHERE tournament_id = ? AND member_id = ?',
                (total_score, group['tournament_id'], member_id)
            )

        conn.commit()

        if action == 'next':
            flash('Hole scores saved.', 'success')
            return redirect(url_for('secure_group_score_entry_by_hole', token=token, hole_number=hole_number + 1))
        elif action == 'previous':
            flash('Hole scores saved.', 'success')
            return redirect(url_for('secure_group_score_entry_by_hole', token=token, hole_number=hole_number - 1))
        elif action == 'finish':
            flash('All scores saved.', 'success')
            return redirect(url_for('secure_group_score_entry', token=token))
        else: # Default action (home)
            flash('Scores saved.', 'success')
            return redirect(url_for('secure_group_score_entry', token=token))

    scores = {}
    running_totals = {}
    front9_totals = {}
    back9_totals = {}
    for member in group_members:
        score_row = conn.execute(
            "SELECT * FROM tournament_scores WHERE tournament_id = ? AND member_id = ?",
            (group['tournament_id'], member['id'])
        ).fetchone()
        
        current_hole_score = ''
        running_total = 0
        front9_total = 0
        back9_total = 0
        
        if score_row:
            current_hole_score = score_row[f'hole{hole_number}'] if score_row[f'hole{hole_number}'] is not None else ''
            
            # Calculate totals from all holes
            all_holes = [score_row[f'hole{i}'] or 0 for i in range(1, 19)]
            front9_total = sum(all_holes[0:9])
            back9_total = sum(all_holes[9:18])
            running_total = front9_total + back9_total
        
        scores[member['id']] = current_hole_score
        running_totals[member['id']] = running_total
        front9_totals[member['id']] = front9_total
        back9_totals[member['id']] = back9_total

    conn.close()
    return render_template('secure_score_entry_by_hole.html',
                         group=group,
                         group_members=group_members,
                         hole_number=hole_number,
                         scores=scores,
                         running_totals=running_totals,
                         front9_totals=front9_totals,
                         back9_totals=back9_totals,
                         token=token,
                         hide_nav=True)

@app.route('/score/<token>/add', methods=['POST'])
def secure_add_group_score(token):
    """Add score for a group member via secure token - restricted to group members only"""
    conn = get_db_connection()
    
    # Get group info by token to verify tournament
    group = conn.execute('''
        SELECT g.*, t.finalized
        FROM groups g
        JOIN tournaments t ON g.tournament_id = t.id
        WHERE g.secure_token = ?
    ''', (token,)).fetchone()
    
    if group is None:
        conn.close()
        flash('Invalid or expired link.', 'error')
        return redirect(url_for('tournaments'))
    
    if group['finalized']:
        conn.close()
        flash('Invalid group or tournament is finalized.', 'error')
        return redirect(url_for('tournaments'))
    
    member_id = int(request.form['member_id'])
    tournament_id = group['tournament_id']
    group_id = group['id']
    
    # Verify that the member is actually in this group
    member_in_group = conn.execute(
        'SELECT 1 FROM group_members WHERE group_id = ? AND member_id = ?',
        (group_id, member_id)
    ).fetchone()
    
    if not member_in_group:
        conn.close()
        flash('Member is not in this group.', 'error')
        return redirect(url_for('tournaments'))
    
    # Check if member already has a score for this tournament
    existing_score = conn.execute(
        'SELECT 1 FROM tournament_scores WHERE tournament_id = ? AND member_id = ?',
        (tournament_id, member_id)
    ).fetchone()
    
    if existing_score:
        conn.close()
        flash('This member already has a score for this tournament.', 'error')
        return redirect(url_for('tournaments'))
    
    # Get all hole scores
    hole_scores = []
    for i in range(1, 19):
        hole_score = int(request.form[f'hole{i}'])
        hole_scores.append(hole_score)
    
    # Calculate total score
    total_score = sum(hole_scores)
    
    # Get member's current handicap
    member_handicap = conn.execute('SELECT handicap FROM members WHERE id = ?', (member_id,)).fetchone()['handicap']

    conn.execute('''
        INSERT INTO tournament_scores (
            tournament_id, member_id, 
            hole1, hole2, hole3, hole4, hole5, hole6, hole7, hole8, hole9,
            hole10, hole11, hole12, hole13, hole14, hole15, hole16, hole17, hole18,
            total_score, net_handicap
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', [tournament_id, member_id] + hole_scores + [total_score, member_handicap])
    
    # Increment tournaments_played for this member
    conn.execute('UPDATE members SET tournaments_played = tournaments_played + 1 WHERE id = ?', (member_id,))
    conn.commit()
    conn.close()
    
    flash('Score submitted.', 'success')
    return redirect(url_for('secure_group_score_entry', token=token))

@app.route('/tournament/<int:tournament_id>/groups/printable')
def printable_group_list(tournament_id):
    conn = get_db_connection()
    
    # Get all groups for this tournament
    groups_query = conn.execute('''
        SELECT id, name, tee_time
        FROM groups
        WHERE tournament_id = ?
    ''', (tournament_id,)).fetchall()

    # Convert to list of dicts to sort in Python
    groups = [dict(row) for row in groups_query]
    groups.sort(key=lambda x: natural_sort_key(x['name']))
    
    group_data = []
    for group in groups:
        members = conn.execute('''
            SELECT m.name, m.handicap
            FROM members m
            JOIN group_members gm ON m.id = gm.member_id
            WHERE gm.group_id = ?
            ORDER BY m.name
        ''', (group['id'],)).fetchall()
        
        group_data.append({
            'name': group['name'],
            'tee_time': group['tee_time'],
            'members': [{'name': member['name'], 'handicap': member['handicap']} for member in members]
        })
        
    conn.close()
    return jsonify(group_data)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5004)
