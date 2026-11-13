"""
EME Chess - correspondence chess over the Moon using WSJT-X (Q65)
W4ATC / NC State

HOW IT WORKS
  * You click a piece, click its destination, then press "Confirm & Send".
  * The move is turned into a short free-text message such as "C007 E2E4"
    and handed to WSJT-X over its UDP interface (loaded into the free-text
    slot; YOU still press Enable Tx in WSJT-X).
  * Decoded messages from WSJT-X are watched. When a message that looks like
    "Cnnn MOVE" arrives and is legal, it is played on your board.
  * The game is saved after every move, so you can close the program
    between EME sessions and pick up where you left off.

REQUIREMENTS
  * Python 3 (tkinter comes with it)
  * pip install chess
  * WSJT-X: File > Settings > Reporting > UDP Server
        address 127.0.0.1, port 2237, and tick "Accept UDP requests"
"""

import json
import os
import queue
import re
import socket
import struct
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

import chess

# ----------------------------------------------------------------------
# Settings you might want to change
# ----------------------------------------------------------------------
UDP_IP = "127.0.0.1"
UDP_PORT = 2237
SAVE_FILE = "eme_chess_game.json"
# Send a station ID after this many seconds of unidentified transmitting.
# The FCC limit is 10 minutes; 8 leaves room for the wait until the next gap.
ID_INTERVAL = 8 * 60

SQ = 72                     # size of one board square in pixels
LIGHT = "#f0d9b5"
DARK = "#b58863"
SELECT = "#f6f669"
PENDING = "#7fd67f"
LASTMOVE = "#cdd26a"

# ----------------------------------------------------------------------
# Dark theme colours
# ----------------------------------------------------------------------
BG = "#1e1f22"          # window background
INPUT_BG = "#141517"    # log box / text entry background
FG = "#e6e6e6"          # normal text
MUTED = "#8a8d93"       # disabled text
BTN = "#34373d"         # button background
BTN_HOVER = "#454953"   # button background when pressed / hovered
ACCENT = "#4ea1ff"      # headings
GOOD = "#5fd35f"
WARN = "#ffb454"
BAD = "#ff6b6b"

# ----------------------------------------------------------------------
# Text shown in the Help window
#   lines starting with "## " are headings, lines indented 4 spaces are
#   shown in a fixed-width font
# ----------------------------------------------------------------------
HELP_TEXT = r"""## What this program does
EME Chess lets two stations play correspondence chess by bouncing each move off the Moon. You click a move on the board and confirm it, and the program hands it to WSJT-X as a short free-text message. When WSJT-X decodes your opponent's message, their move appears on your board automatically.

## One-time computer setup
1. Install Python 3 from python.org. On the first installer screen, tick "Add Python to PATH".
2. Open a Command Prompt and type:
    pip install chess
3. Put eme_chess.py in a folder of its own, for example C:\EMEChess
4. Start the program from the Command Prompt:
    cd C:\EMEChess
    python eme_chess.py
The game is saved in the same folder as eme_chess_game.json after every move, so you can close the program between sessions and pick up where you left off.

## One-time WSJT-X setup
1. In WSJT-X choose File > Settings > Reporting.
2. In the "UDP Server" section set:
    UDP Server:              127.0.0.1
    UDP Server port number:  2237
   and tick "Accept UDP requests". Click OK.
3. Choose Mode > Q65 and set the sub-mode and period you and your opponent have agreed on (for example 30B: 30-second period, sub-mode B).
4. Agree with your opponent on frequencies and on who transmits in the first period and who in the second (the "Tx even/1st" checkbox).
5. Untick "Auto Seq" on the main WSJT-X window, so it does not answer station-ID messages by itself.
6. Leave WSJT-X running. Within about 15 seconds the top of this window should change to a green "WSJT-X: connected".

## Playing
- Agree on sides beforehand. White moves first.
- Click one of your pieces, then click its destination. Illegal moves are refused.
- Press "Confirm & Send". The move is loaded into WSJT-X's free-text message. You must then press Enable Tx in WSJT-X to actually transmit; this program never keys your transmitter by itself.
- WSJT-X repeats the message each transmit period until you disable Tx. That gives your opponent several chances to decode it, and duplicates are ignored automatically.
- When your opponent's move is decoded it is played on your board and shown in the log with its signal report.
- Castling: move the king two squares. Promotion: you will be asked which piece you want.
- "Re-send last move" loads your last message into WSJT-X again.
- "HALT TX" tells WSJT-X to stop transmitting immediately.

## Draws and resigning
- "Offer draw" is available while you are waiting for your opponent. It re-sends your last move with a draw offer attached.
- If your opponent offers a draw, "Accept draw offer" becomes available. To decline, simply play a move; the program marks it with an X so your opponent knows.
- "Resign" is available on your turn and is sent in place of a move.

## What goes over the air
Q65 free text is limited to 13 characters, so messages are kept short:
    C007 E2E4       move number 7: e2 to e4
    C012 E7E8Q      a pawn promoting to a queen
    C007 E2E4 D?    a move with a draw offer
    C008 XE7E5      a move that declines a draw offer
    C008 DRAW.      accept a draw
    C008 RESIGN     resign
The number is the move count (each side's move counts once), which lets the program ignore repeats and notice missed moves.

## Station identification (call sign)
FCC rules (Part 97.119) require your station to transmit its call sign at the end of each communication and at least every 10 minutes during one. Chess moves do not carry a call sign, so this program does it for you.
- Enter both call signs with the "Callsigns..." button. Your own is picked up from WSJT-X automatically when it can.
- While you are transmitting, the program keeps a countdown. After 8 minutes without an ID, it swaps in a normal Q65 message for one transmission, then puts your move message back. There is nothing for you to do:
    N4XYZ W4ATC
- "Send ID now" does the same thing on demand.
- "Final ID (73)" sends the closing ID and then stops WSJT-X's transmitter:
    N4XYZ W4ATC 73
  Press it when you have finished for the session or when the game is over, instead of just switching Tx off. The program also asks when you close it.
- Your opponent is responsible for identifying their own station under their own country's rules.

## Troubleshooting
- Still "not connected": WSJT-X must be running, and the three Reporting settings above must match exactly (127.0.0.1, 2237, Accept UDP requests).
- Error box about the UDP port: another program (JTAlert, GridTracker and similar) is already using port 2237. Close it while playing.
- Nothing is transmitted: press Enable Tx in WSJT-X, and check the mode, frequency and Tx even/1st settings.
- "OUT OF SYNC": a move was missed. Ask your opponent to press "Re-send last move".
- Try it without a radio: type a message such as C001 E2E4 into the "Test receive" box and press Go.
- Both players should use the same version of this program.
"""

# ----------------------------------------------------------------------
# WSJT-X UDP protocol (just the pieces we need)
# ----------------------------------------------------------------------
MAGIC = 0xADBCCBDA
SCHEMA = 2
MSG_STATUS = 1
MSG_DECODE = 2
MSG_HALT_TX = 8
MSG_FREE_TEXT = 9

# Message formats on the air (13 characters max in Q65 free text):
#   C007 E2E4       a move (ply number 007)
#   C008 XE7E5      a move that also DECLINES a draw offer
#   C007 E2E4 D?    a move with a draw offer attached
#   C008 DRAW.      accept a draw offer (sent instead of a move)
#   C008 RESIGN     resign (sent instead of a move)
# A trailing "?" from a low-confidence decode is tolerated.
MOVE_RE = re.compile(r"^C(\d{3}) (X?)([A-H][1-8][A-H][1-8][QRBN]?)( D\?)?\??$")
CMD_RE = re.compile(r"^C(\d{3}) (RESIGN|DRAW\.)\??$")


def _utf8(text):
    raw = text.encode("utf-8")
    return struct.pack(">I", len(raw)) + raw


class Reader:
    """Tiny helper to pull values out of a WSJT-X packet."""

    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, fmt):
        values = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += struct.calcsize(fmt)
        return values[0] if len(values) == 1 else values

    def utf8(self):
        n = self.take(">I")
        if n == 0xFFFFFFFF:
            return ""
        text = self.data[self.pos:self.pos + n].decode("utf-8", "replace")
        self.pos += n
        return text


class WsjtxLink:
    """Listens for WSJT-X decodes and sends it free-text messages."""

    def __init__(self, inbox):
        self.inbox = inbox
        self.addr = None            # where WSJT-X is (learned from its packets)
        self.client_id = "WSJT-X"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((UDP_IP, UDP_PORT))
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        announced = False
        while True:
            try:
                data, addr = self.sock.recvfrom(65535)
            except OSError:
                break
            try:
                r = Reader(data)
                magic, _schema, mtype = r.take(">III")
                if magic != MAGIC:
                    continue
                self.client_id = r.utf8() or self.client_id
                self.addr = addr
                if not announced:
                    announced = True
                    self.inbox.put(("connected", self.client_id))
                if mtype == MSG_DECODE:
                    is_new = r.take(">?")
                    r.take(">I")            # time of day
                    snr = r.take(">i")
                    r.take(">d")            # delta time
                    r.take(">I")            # delta frequency
                    r.utf8()                # mode character
                    message = r.utf8()
                    if is_new:
                        self.inbox.put(("decode", snr, message))
                elif mtype == MSG_STATUS:
                    r.take(">Q")            # dial frequency
                    r.utf8()                # mode
                    dx_call = r.utf8()
                    r.utf8()                # report
                    r.utf8()                # tx mode
                    tx_enabled = r.take(">?")
                    transmitting = r.take(">?")
                    r.take(">?")            # decoding
                    r.take(">I")            # rx df
                    r.take(">I")            # tx df
                    de_call = r.utf8()
                    tx_message = None       # only newer WSJT-X versions send it
                    try:
                        r.utf8()            # de grid
                        r.utf8()            # dx grid
                        r.take(">?")        # tx watchdog
                        r.utf8()            # sub-mode
                        r.take(">?")        # fast mode
                        r.take(">B")        # special operation mode
                        r.take(">I")        # frequency tolerance
                        r.take(">I")        # T/R period
                        r.utf8()            # configuration name
                        tx_message = r.utf8()
                    except Exception:
                        pass
                    self.inbox.put(("status", tx_enabled, transmitting,
                                    de_call, dx_call, tx_message))
            except Exception:
                continue                    # ignore anything we can't parse

    @property
    def connected(self):
        return self.addr is not None

    def send_free_text(self, text):
        if not self.addr:
            return False
        packet = (struct.pack(">III", MAGIC, SCHEMA, MSG_FREE_TEXT)
                  + _utf8(self.client_id) + _utf8(text)
                  + struct.pack(">?", True))
        self.sock.sendto(packet, self.addr)
        return True

    def halt_tx(self):
        if not self.addr:
            return False
        packet = (struct.pack(">III", MAGIC, SCHEMA, MSG_HALT_TX)
                  + _utf8(self.client_id) + struct.pack(">?", False))
        self.sock.sendto(packet, self.addr)
        return True


# ----------------------------------------------------------------------
# The chess application
# ----------------------------------------------------------------------
GLYPH = {"p": "\u265F", "n": "\u265E", "b": "\u265D",
         "r": "\u265C", "q": "\u265B", "k": "\u265A"}


class ChessApp:
    def __init__(self, root, link, inbox):
        self.root = root
        self.link = link
        self.inbox = inbox

        self.board = chess.Board()
        self.my_color = chess.WHITE
        self.selected = None
        self.pending = None
        self.last_text = ""
        self.offer_in = False       # opponent has offered us a draw
        self.offer_out = False      # we have offered the opponent a draw
        self.ended = None           # text describing how the game ended
        self.my_call = ""
        self.opp_call = ""
        self.transmitting = False   # WSJT-X is on the air right now
        self.tx_enabled = False
        self.unid_since = None      # when unidentified transmitting began
        self.last_id = None
        self.id_stage = None        # None / "loaded" / "sending"
        self.id_kind = "id"
        self.id_text = ""
        self.id_request = None      # "id" / "final" waiting for a gap
        self.id_warned = False

        root.configure(bg=BG)
        root.option_add("*Background", BG)
        root.option_add("*Foreground", FG)
        root.option_add("*Button.Background", BTN)
        root.option_add("*Button.Foreground", FG)
        root.option_add("*Button.activeBackground", BTN_HOVER)
        root.option_add("*Button.activeForeground", "white")
        root.option_add("*Button.disabledForeground", MUTED)
        root.option_add("*Button.relief", "flat")
        root.option_add("*Button.borderWidth", 0)
        root.option_add("*Button.padY", 4)
        root.title("EME Chess - W4ATC")
        self.canvas = tk.Canvas(root, width=8 * SQ, height=8 * SQ,
                                highlightthickness=0)
        self.canvas.grid(row=0, column=0, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self.on_click)

        panel = tk.Frame(root)
        panel.grid(row=0, column=1, sticky="ns", padx=8, pady=8)

        top = tk.Frame(panel)
        top.pack(fill="x")
        tk.Button(top, text="?  Help", command=self.show_help,
                  width=9).pack(side="right")
        self.conn_label = tk.Label(top, text="WSJT-X: not connected (yet)",
                                   fg=BAD, anchor="w")
        self.conn_label.pack(side="left", fill="x", expand=True)
        self.status_label = tk.Label(panel, text="", font=("Segoe UI", 12, "bold"),
                                     anchor="w", wraplength=330, justify="left")
        self.status_label.pack(fill="x", pady=6)
        self.id_label = tk.Label(panel, text="", font=("Segoe UI", 9), anchor="w")
        self.id_label.pack(fill="x", pady=(0, 6))

        self.confirm_btn = tk.Button(panel, text="Confirm && Send".replace("&&", "&"),
                                     command=self.confirm, state="disabled",
                                     height=2)
        self.confirm_btn.pack(fill="x", pady=2)
        self.cancel_btn = tk.Button(panel, text="Cancel move",
                                    command=self.cancel, state="disabled")
        self.cancel_btn.pack(fill="x", pady=2)
        tk.Button(panel, text="Re-send last move",
                  command=self.resend).pack(fill="x", pady=2)
        self.offer_btn = tk.Button(panel, text="Offer draw",
                                   command=self.offer_draw, state="disabled")
        self.offer_btn.pack(fill="x", pady=2)
        self.accept_btn = tk.Button(panel, text="Accept draw offer",
                                    command=self.accept_draw, state="disabled")
        self.accept_btn.pack(fill="x", pady=2)
        self.resign_btn = tk.Button(panel, text="Resign",
                                    command=self.resign, state="disabled")
        self.resign_btn.pack(fill="x", pady=2)
        tk.Button(panel, text="HALT TX", fg="white", bg="#8b2323",
                  activebackground="#b03030",
                  command=self.halt).pack(fill="x", pady=2)
        tk.Button(panel, text="New game...",
                  command=self.new_game).pack(fill="x", pady=2)
        row = tk.Frame(panel)
        row.pack(fill="x", pady=2)
        for label, cmd in (("Send ID now", self.id_now),
                           ("Final ID (73)", self.id_final),
                           ("Callsigns...", self.ask_callsigns)):
            tk.Button(row, text=label, command=cmd).pack(
                side="left", expand=True, fill="x", padx=1)

        self.log_box = tk.Text(panel, width=44, height=16, state="disabled",
                               wrap="word", bg=INPUT_BG, fg=FG, relief="flat",
                               highlightthickness=0, padx=6, pady=6,
                               font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, pady=6)

        test = tk.Frame(panel)
        test.pack(fill="x")
        tk.Label(test, text="Test receive:").pack(side="left")
        self.test_entry = tk.Entry(test, width=14, bg=INPUT_BG, fg=FG,
                                   insertbackground=FG, relief="flat")
        self.test_entry.pack(side="left", padx=4)
        tk.Button(test, text="Go", command=self.test_receive).pack(side="left")

        if os.path.exists(SAVE_FILE):
            self.load()
            if not (self.my_call and self.opp_call):
                self.ask_callsigns()
        else:
            self.new_game(first_time=True)
            self.show_help()
        self.refresh()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(200, self.poll)
        self.root.after(1000, self.id_tick)

    # ---------------- helpers ----------------
    def log(self, text):
        stamp = time.strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"{stamp}  {text}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def refresh(self):
        self.draw()
        self.update_status()

    def game_over_text(self):
        if self.ended:
            return self.ended
        b = self.board
        if b.is_checkmate():
            return "Checkmate! Result " + b.result()
        if b.is_game_over():
            return "Game over (draw). Result " + b.result()
        return None

    def update_status(self):
        over = self.game_over_text()
        side = "White" if self.my_color == chess.WHITE else "Black"
        if over:
            text = over
        elif self.pending:
            text = f"Pending move {self.pending.uci().upper()} - confirm to send"
        elif self.board.turn == self.my_color:
            text = f"You are {side}. YOUR MOVE."
            if self.offer_in:
                text += ("\nOpponent has OFFERED A DRAW. Accept it, "
                         "or just play a move to decline.")
        else:
            text = f"You are {side}. Waiting for opponent's move..."
            if self.offer_out:
                text += "\nDraw offer sent."
        self.status_label.config(text=text)
        state = "normal" if self.pending else "disabled"
        self.confirm_btn.config(state=state)
        self.cancel_btn.config(state=state)
        my_turn = (not over) and self.board.turn == self.my_color
        waiting = (not over) and self.board.turn != self.my_color
        self.accept_btn.config(state="normal" if (
            my_turn and self.offer_in and not self.pending) else "disabled")
        self.resign_btn.config(state="normal" if my_turn else "disabled")
        self.offer_btn.config(state="normal" if (
            waiting and self.board.move_stack and not self.offer_out) else "disabled")

    # ---------------- drawing ----------------
    def draw(self):
        c = self.canvas
        c.delete("all")
        flip = self.my_color == chess.BLACK
        last = self.board.peek() if self.board.move_stack else None
        font = ("Segoe UI Symbol", int(SQ * 0.68))
        small = ("Segoe UI", 8)
        for sq in chess.SQUARES:
            f, r = chess.square_file(sq), chess.square_rank(sq)
            x = 7 - f if flip else f
            y = r if flip else 7 - r
            x0, y0 = x * SQ, y * SQ
            colour = LIGHT if (f + r) % 2 else DARK
            if sq == self.selected:
                colour = SELECT
            elif self.pending and sq in (self.pending.from_square,
                                         self.pending.to_square):
                colour = PENDING
            elif last and sq in (last.from_square, last.to_square):
                colour = LASTMOVE
            c.create_rectangle(x0, y0, x0 + SQ, y0 + SQ, fill=colour, outline="")
            if y == 7:
                c.create_text(x0 + SQ - 8, y0 + SQ - 8, text="abcdefgh"[f],
                              font=small, fill="#555")
            if x == 0:
                c.create_text(x0 + 8, y0 + 8, text=str(r + 1),
                              font=small, fill="#555")
            piece = self.board.piece_at(sq)
            if piece:
                cx, cy = x0 + SQ // 2, y0 + SQ // 2
                glyph = GLYPH[piece.symbol().lower()]
                if piece.color == chess.WHITE:
                    for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1),
                                   (0, 2), (0, -2), (2, 0), (-2, 0)):
                        c.create_text(cx + dx, cy + dy, text=glyph,
                                      font=font, fill="black")
                    c.create_text(cx, cy, text=glyph, font=font, fill="white")
                else:
                    c.create_text(cx, cy, text=glyph, font=font, fill="black")

    # ---------------- user moves ----------------
    def on_click(self, event):
        if self.pending or self.board.turn != self.my_color:
            return
        if self.game_over_text():
            return
        x, y = event.x // SQ, event.y // SQ
        if not (0 <= x < 8 and 0 <= y < 8):
            return
        flip = self.my_color == chess.BLACK
        f = 7 - x if flip else x
        r = y if flip else 7 - y
        sq = chess.square(f, r)
        piece = self.board.piece_at(sq)

        if self.selected is None or (piece and piece.color == self.my_color):
            self.selected = sq if (piece and piece.color == self.my_color) else None
        else:
            move = chess.Move(self.selected, sq)
            mover = self.board.piece_at(self.selected)
            if mover.piece_type == chess.PAWN and chess.square_rank(sq) in (0, 7):
                if chess.Move(self.selected, sq, chess.QUEEN) in self.board.legal_moves:
                    ans = (simpledialog.askstring(
                        "Promotion", "Promote to (Q, R, B, N):",
                        initialvalue="Q", parent=self.root) or "Q").upper()
                    promo = {"Q": chess.QUEEN, "R": chess.ROOK,
                             "B": chess.BISHOP, "N": chess.KNIGHT}.get(ans[:1], chess.QUEEN)
                    move = chess.Move(self.selected, sq, promo)
            if move in self.board.legal_moves:
                self.pending = move
            else:
                self.log("That move is not legal.")
            self.selected = None
        self.refresh()

    def cancel(self):
        self.pending = None
        self.selected = None
        self.refresh()

    def confirm(self):
        move = self.pending
        if not move:
            return
        decline = False
        if self.offer_in:
            if not messagebox.askyesno(
                    "Draw offer", "Your opponent has offered a draw.\n\n"
                    "Playing this move DECLINES the offer. Continue?"):
                return
            decline = True
        seq = len(self.board.move_stack) + 1
        san = self.board.san(move)
        self.board.push(move)
        self.pending = None
        self.selected = None
        self.offer_in = False
        self.last_text = f"C{seq:03d} {'X' if decline else ''}{move.uci().upper()}"
        if decline:
            self.log("You declined the draw offer.")
        self.save()
        self.log(f"You played {san}")
        self.transmit()
        over = self.game_over_text()
        if over:
            self.log(over)
        self.refresh()

    def transmit(self):
        if not self.last_text:
            self.log("Nothing to send yet.")
            return
        if self.id_stage:
            self.log("A station ID is queued - your move goes out right after it.")
            return
        if self.link.send_free_text(self.last_text):
            self.log(f"Loaded '{self.last_text}' into WSJT-X. "
                     "Press Enable Tx there to transmit.")
        else:
            self.log("WSJT-X not connected - move saved but NOT loaded. "
                     "Use 'Re-send last move' once WSJT-X is talking to us.")

    def resend(self):
        self.transmit()

    def halt(self):
        if self.link.halt_tx():
            self.log("Sent HALT TX to WSJT-X.")
        else:
            self.log("WSJT-X not connected.")

    # ---------------- draw / resign ----------------
    def end_game(self, text):
        self.ended = text
        self.pending = None
        self.selected = None
        self.offer_in = False
        self.offer_out = False
        self.save()
        self.log(text)
        self.refresh()

    def offer_draw(self):
        text = self.last_text + " D?"
        if len(text) > 13:
            messagebox.showinfo("Cannot fit",
                                "That message is too long to carry a draw offer "
                                "(Q65 free text is limited to 13 characters).\n"
                                "Offer the draw after your next move instead.")
            return
        if not messagebox.askyesno("Offer draw",
                                   "Offer your opponent a draw?\n\n"
                                   f"Will transmit: {text}"):
            return
        self.offer_out = True
        self.last_text = text
        self.save()
        self.log("Draw offered.")
        self.transmit()
        self.refresh()

    def accept_draw(self):
        if not messagebox.askyesno("Accept draw", "Accept the draw offer?"):
            return
        seq = len(self.board.move_stack) + 1
        self.last_text = f"C{seq:03d} DRAW."
        self.end_game("Draw agreed. Result 1/2-1/2")
        self.transmit()

    def resign(self):
        if not messagebox.askyesno("Resign", "Really resign this game?"):
            return
        seq = len(self.board.move_stack) + 1
        self.last_text = f"C{seq:03d} RESIGN"
        result = "0-1" if self.my_color == chess.WHITE else "1-0"
        self.end_game(f"You resigned. Result {result}")
        self.transmit()

    # ---------------- receiving ----------------
    def poll(self):
        try:
            while True:
                item = self.inbox.get_nowait()
                if item[0] == "connected":
                    self.conn_label.config(text=f"WSJT-X: connected ({item[1]})",
                                           fg=GOOD)
                elif item[0] == "decode":
                    self.handle_message(item[2], item[1])
                elif item[0] == "status":
                    self.on_status(*item[1:])
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    def test_receive(self):
        self.handle_message(self.test_entry.get(), 0)

    def handle_message(self, text, snr):
        clean = text.strip().upper()
        if self.ended:
            return
        ply = len(self.board.move_stack)
        opp_turn = self.board.turn != self.my_color     # we are waiting on them

        # --- resign / accept draw (take the place of the opponent's move) ---
        c = CMD_RE.match(clean)
        if c:
            seq, word = int(c.group(1)), c.group(2)
            if not opp_turn or seq <= ply:
                return
            if seq != ply + 1:
                self.log(f"OUT OF SYNC: got #{seq}, expected #{ply + 1}.")
                return
            if word == "RESIGN":
                result = "1-0" if self.my_color == chess.WHITE else "0-1"
                self.log(f"RECEIVED '{clean}' (SNR {snr} dB)")
                self.end_game(f"Opponent resigned - you win! Result {result}")
            elif self.offer_out:
                self.log(f"RECEIVED '{clean}' (SNR {snr} dB)")
                self.end_game("Draw agreed. Result 1/2-1/2")
            else:
                self.log("Received DRAW. but no offer was made - ignored.")
            return

        # --- ordinary move ---
        m = MOVE_RE.match(clean)
        if not m:
            return                                  # not a chess message
        seq, declined = int(m.group(1)), bool(m.group(2))
        uci, offer = m.group(3).lower(), bool(m.group(4))

        if not opp_turn:
            # We are already up to date. This may be a repeat of the opponent's
            # last move that now carries a draw offer.
            if (seq == ply and offer and not self.offer_in and ply > 0
                    and self.board.peek().uci() == uci):
                self.offer_in = True
                self.log("Opponent OFFERS A DRAW.")
                self.save()
                self.refresh()
            return
        if seq <= ply:
            return                                  # our own echo / duplicate
        if seq != ply + 1:
            self.log(f"OUT OF SYNC: got move #{seq}, expected #{ply + 1}. "
                     "Ask opponent to re-send.")
            return
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return
        if move not in self.board.legal_moves:
            self.log(f"Received '{clean}' but it is not legal here - ignored.")
            return
        san = self.board.san(move)
        self.board.push(move)
        self.log(f"RECEIVED {san}  ({clean}, SNR {snr} dB)")
        if self.offer_out:
            self.offer_out = False
            self.log("Opponent DECLINED your draw offer." if declined
                     else "Opponent moved on - draw offer considered declined.")
        if offer:
            self.offer_in = True
            self.log("Opponent OFFERS A DRAW.")
        self.save()
        over = self.game_over_text()
        if over:
            self.log(over)
        self.refresh()

    # ---------------- station identification ----------------
    def ask_callsigns(self):
        me = simpledialog.askstring("Callsigns", "YOUR callsign:",
                                    initialvalue=self.my_call, parent=self.root)
        if me and me.strip():
            self.my_call = me.strip().upper()
        opp = simpledialog.askstring("Callsigns", "OPPONENT's callsign:",
                                     initialvalue=self.opp_call, parent=self.root)
        if opp and opp.strip():
            self.opp_call = opp.strip().upper()
        for call in (self.my_call, self.opp_call):
            if "/" in call:
                self.log(f"Note: '{call}' has a slash; ID messages work best "
                         "with plain callsigns.")
        self.save()

    def ensure_calls(self):
        if not (self.my_call and self.opp_call):
            self.ask_callsigns()
        return bool(self.my_call and self.opp_call)

    def id_now(self):
        if not self.ensure_calls():
            return
        if not self.link.connected:
            self.log("WSJT-X not connected - cannot load an ID.")
            return
        self.id_request = "id"
        self.log("ID requested - it goes out at the next gap between transmissions.")
        self.maybe_queue_id()

    def id_final(self):
        if not self.ensure_calls():
            return
        if not self.link.connected:
            self.log("WSJT-X not connected - cannot load an ID.")
            return
        self.id_request = "final"
        self.log("Final ID (73) requested - it goes out at the next gap between "
                 "transmissions. Make sure Enable Tx is on.")
        self.maybe_queue_id()

    def maybe_queue_id(self):
        """Load an ID into WSJT-X if one is due or requested, but only in the
        gap between transmissions so we never change a message mid-period."""
        if self.id_stage or self.transmitting:
            return
        due = (self.unid_since is not None
               and time.time() - self.unid_since >= ID_INTERVAL)
        if not (self.id_request or due):
            return
        if not (self.my_call and self.opp_call):
            if not self.id_warned:
                self.id_warned = True
                self.log("A station ID is due but the callsigns are not set - "
                         "press 'Callsigns...'.")
            return
        if not self.link.connected:
            return
        kind = self.id_request or "id"
        self.id_request = None
        text = f"{self.opp_call} {self.my_call}" + (" 73" if kind == "final" else "")
        if self.link.send_free_text(text):
            self.id_stage = "loaded"
            self.id_kind = kind
            self.id_text = text
            self.log(f"Station ID '{text}' loaded into WSJT-X.")

    def finish_id(self, now):
        kind = self.id_kind
        self.id_stage = None
        self.unid_since = None
        self.last_id = now
        self.id_warned = False
        if kind == "final":
            self.link.halt_tx()
            self.log("Final ID sent - Tx halted. 73!")
            return
        self.log("Station ID sent.")
        if self.last_text:
            self.link.send_free_text(self.last_text)
            self.log(f"Move message '{self.last_text}' put back in WSJT-X.")
        else:
            self.link.halt_tx()
        self.maybe_queue_id()

    def on_status(self, tx_enabled, transmitting, de_call, dx_call, tx_message):
        now = time.time()
        if de_call and not self.my_call:
            self.my_call = de_call.strip().upper()
            self.log(f"Your callsign ({self.my_call}) was taken from WSJT-X.")
            self.save()
        was_tx, was_en = self.transmitting, self.tx_enabled
        self.transmitting, self.tx_enabled = transmitting, tx_enabled

        if tx_enabled and not was_en and self.unid_since is None and not self.id_stage:
            self.unid_since = now               # the ID clock starts

        if transmitting and not was_tx:         # a transmission just began
            sending_id = False
            if self.id_stage:
                if tx_message:
                    sending_id = tx_message.strip().upper() == self.id_text
                else:
                    sending_id = True
            if sending_id:
                self.id_stage = "sending"
            elif self.unid_since is None:
                self.unid_since = now
        elif was_tx and not transmitting:       # a transmission just ended
            if self.id_stage == "sending":
                self.finish_id(now)
            else:
                self.maybe_queue_id()

        if (was_en and not tx_enabled and self.unid_since is not None
                and not self.id_stage):
            self.log("Tx was switched off but you have transmitted since your "
                     "last ID. When you are finished, press 'Final ID (73)'.")

    def id_tick(self):
        self.maybe_queue_id()
        now = time.time()
        colour = FG
        if self.id_stage == "loaded":
            text, colour = "Station ID queued - goes out on the next transmission", WARN
        elif self.id_stage == "sending":
            text, colour = "Transmitting station ID...", WARN
        elif self.unid_since is None:
            last = (time.strftime("%H:%M", time.localtime(self.last_id))
                    if self.last_id else "none yet")
            text, colour = f"Station ID: all clear (last ID {last})", GOOD
        elif self.game_over_text():
            text, colour = "Game over - press Final ID (73) when you are done", WARN
        else:
            left = int(ID_INTERVAL - (now - self.unid_since))
            if left > 0:
                text = f"Next station ID in {left // 60}:{left % 60:02d}"
                colour = FG if left > 120 else WARN
            else:
                text, colour = "Station ID due now", BAD
        self.id_label.config(text=text, fg=colour)
        self.root.after(1000, self.id_tick)

    def on_close(self):
        if self.id_stage:
            if not messagebox.askyesno("Station ID",
                                       "A station ID is queued or being sent.\n\n"
                                       "Close anyway?"):
                return
        elif self.unid_since is not None:
            ans = messagebox.askyesnocancel(
                "Station ID",
                "You have transmitted since your last station ID.\n\n"
                "Yes = queue a final ID (73) and keep the program open\n"
                "No = close anyway\nCancel = go back")
            if ans is None:
                return
            if ans:
                self.id_final()
                return
        self.root.destroy()

    # ---------------- help ----------------
    def show_help(self):
        if getattr(self, "help_win", None) and self.help_win.winfo_exists():
            self.help_win.lift()
            return
        win = tk.Toplevel(self.root)
        self.help_win = win
        win.title("EME Chess - Help")
        win.geometry("680x640")
        win.configure(bg=BG)
        bar = tk.Scrollbar(win)
        bar.pack(side="right", fill="y")
        box = tk.Text(win, wrap="word", bg=INPUT_BG, fg=FG, relief="flat",
                      highlightthickness=0, padx=16, pady=12,
                      font=("Segoe UI", 10), yscrollcommand=bar.set,
                      spacing1=2, spacing3=2)
        box.pack(side="left", fill="both", expand=True)
        bar.config(command=box.yview)
        box.tag_configure("h", font=("Segoe UI", 13, "bold"), foreground=ACCENT,
                          spacing1=14, spacing3=4)
        box.tag_configure("mono", font=("Consolas", 10), lmargin1=24, lmargin2=24,
                          foreground="#b8d8ff")
        for line in HELP_TEXT.splitlines():
            if line.startswith("## "):
                box.insert("end", line[3:] + "\n", "h")
            elif line.startswith("    "):
                box.insert("end", line[4:] + "\n", "mono")
            else:
                box.insert("end", line + "\n")
        box.config(state="disabled")

    # ---------------- game management ----------------
    def new_game(self, first_time=False):
        if not first_time and not messagebox.askyesno(
                "New game", "Discard the current game and start a new one?"):
            return
        white = messagebox.askyesno("Choose side",
                                    "Will YOU play White?\n\n"
                                    "(Yes = White, moves first. No = Black.)")
        self.board = chess.Board()
        self.my_color = chess.WHITE if white else chess.BLACK
        self.pending = None
        self.selected = None
        self.last_text = ""
        self.offer_in = self.offer_out = False
        self.ended = None
        self.ask_callsigns()
        self.save()
        self.log("New game started. You are " + ("White." if white else "Black."))
        self.refresh()

    def save(self):
        data = {"my_color": "white" if self.my_color == chess.WHITE else "black",
                "moves": [m.uci() for m in self.board.move_stack],
                "last_text": self.last_text,
                "offer_in": self.offer_in, "offer_out": self.offer_out,
                "ended": self.ended,
                "my_call": self.my_call, "opp_call": self.opp_call}
        with open(SAVE_FILE, "w") as fh:
            json.dump(data, fh)

    def load(self):
        try:
            with open(SAVE_FILE) as fh:
                data = json.load(fh)
            self.my_color = chess.WHITE if data["my_color"] == "white" else chess.BLACK
            self.board = chess.Board()
            for uci in data["moves"]:
                self.board.push_uci(uci)
            self.last_text = data.get("last_text", "")
            self.offer_in = data.get("offer_in", False)
            self.offer_out = data.get("offer_out", False)
            self.ended = data.get("ended")
            self.my_call = data.get("my_call", "")
            self.opp_call = data.get("opp_call", "")
            self.log(f"Resumed saved game ({len(self.board.move_stack)} moves played).")
        except Exception as err:
            self.log(f"Could not load saved game: {err}")


def main():
    root = tk.Tk()
    inbox = queue.Queue()
    try:
        link = WsjtxLink(inbox)
    except OSError as err:
        messagebox.showerror(
            "Cannot open UDP port",
            f"Could not listen on {UDP_IP}:{UDP_PORT}\n\n{err}\n\n"
            "Another program (JTAlert, GridTracker, ...) may be using it.")
        return
    ChessApp(root, link, inbox)
    root.mainloop()


if __name__ == "__main__":
    main()
