# EME-Chess
A simple python script that interfaces with WSJT-X to coordinate and provide a GUI for over-the-air chess games via earth-moon-earth amateur radio communication.
Works directly with WSJT-X.
Download eme-chess.py and put it in a folder on your drive called "C:\EMEChess"
Ensure that you have Python 3 or newer installed on your machine. 
During installation ensure that you check "Add Python to PATH" so that pip and python commands are useable in Command Prompt. 
Open Command Prompt and type "pip install chess". If that doesnt work, try "python -m pip install chess" or "py -m pip install chess"

Now you should be good to go ahead and open the program. In Command Prompt, navigate to the folder where you saved the program. i.e. "cd C:\EMEChess" once there, enter the command "python eme_chess.py" to start the program.

Now that you have the program installed, it needs to be set up to interface with WSJT-X. Open WSJT-X and simply navigate to File->Settings->Reporting->UDP Server, then set the address to 127.0.0.1 and port to 2237, and activate "Accept UDP requests"
Close out WSJT-X and restart the program. 

Now you should be able to start a new game. Agree on who will play white before starting the game. Moves are encoded as follows: "Cnnn XkXk" where n is the number of moves since the start of the game, X is a column letter and k is a row number. For instance, the opening 1.e4e5 2.Nf3Nc6 in standard algebraic chess notation would be encoded as the following in EME chess, assuming station1 is white and station2 is black:
station1: "C001 E2E4"
station2: "C002 E7E5"
station1: "C003 G1F3"
station2: "C004 B8C6"

Note that in order to adhere to the 10-minute ID limit, the program will automatically send your callsign to WSJT-X once every 8 minutes, delaying the game by a turn. You may manually ID by clicking the "send ID now" button. Also, you can offer/accept a draw or resign, just like on other correspondence chess platforms. 

Now you are all set up to start playing chess on the moon!
