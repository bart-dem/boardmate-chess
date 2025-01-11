import os
import chess
import chess.engine
from flask import Flask, render_template, request, jsonify
import atexit
import logging

app = Flask(__name__)

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ścieżka do pliku Stockfisha
STOCKFISH_PATH = '/opt/homebrew/bin/stockfish'  # Upewnij się, że ścieżka jest poprawna

# Uruchamiamy silnik przy starcie aplikacji
try:
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    logger.info("Stockfish engine started successfully.")
except Exception as e:
    logger.error(f"Failed to start Stockfish engine: {e}")
    raise e

# Rejestrujemy funkcję zamykającą silnik przy zamknięciu aplikacji
@atexit.register
def shutdown_engine():
    try:
        engine.quit()
        logger.info("Stockfish engine shut down successfully.")
    except Exception as e:
        logger.error(f"Error shutting down Stockfish engine: {e}")

# Globalna plansza (tylko do prototypu!)
board = chess.Board()

def get_move_history(board):
    """
    Tworzy sformatowaną historię ruchów w formacie "1. e4 e5 2. Nf3 Nc6 3. d4 d5"
    """
    move_history = []
    temp_board = chess.Board()
    logger.info("Generating move history...")

    for i, move in enumerate(board.move_stack):
        try:
            san_move = temp_board.san(move)
            logger.info(f"Move {i + 1}: {san_move}")
        except ValueError as e:
            san_move = "???"
            logger.error(f"Error converting move to SAN: {e}")

        # Najpierw uzyskaj SAN dla ruchu w bieżącym stanie planszy
        if i % 2 == 0:
            # Numer ruchu + ruch gracza
            move_str = f"{i//2 + 1}. {san_move}"
            logger.info(f"Start move pair: {move_str}")
        else:
            # Ruch komputera
            move_str += f" {san_move}"
            logger.info(f"Completed move pair: {move_str}")
            move_history.append(move_str)

        # Następnie wykonaj ruch na planszy tymczasowej
        temp_board.push(move)

    if len(board.move_stack) % 2 != 0:
        # Jeśli jest nieparzysta liczba ruchów, dodaj ostatni ruch gracza
        logger.info(f"Odd number of moves, adding last move: {move_str}")
        move_history.append(move_str)

    history_str = ' '.join(move_history)
    logger.info(f"Final move history: {history_str}")
    return history_str

@app.route("/")
def index():
    """
    Renderuje stronę główną z interfejsem gry szachowej.
    """
    return render_template("index.html")

@app.route("/newgame", methods=["POST"])
def new_game():
    """
    Inicjalizuje nową grę szachową.
    """
    global board
    board = chess.Board()
    logger.info("New game started.")
    return jsonify({
        "status": "ok",
        "fen": board.fen(),
        "moveHistory": ""
    })

@app.route("/getmoves", methods=["GET"])
def get_moves():
    """
    Zwraca listę dozwolonych ruchów w notacji SAN do wyświetlenia w dropdownie.
    """
    try:
        moves = [board.san(move) for move in board.legal_moves]
        logger.info("Retrieved legal moves for current position.")
    except Exception as e:
        logger.error(f"Error retrieving legal moves: {e}")
        return jsonify({"error": str(e)}), 500
    return jsonify({"moves": moves})

@app.route("/move", methods=["POST"])

def player_move():
    """
    Odbiera ruch gracza (w notacji SAN), wykonuje go, 
    a następnie generuje ruch komputera. Zwraca historię ruchów i aktualny stan gry.
    """
    global board

    data = request.json
    san_move = data.get("move")  # Ruch gracza w notacji SAN
    logger.info(f"Received player move: {san_move}")

    # 1. Wykonaj ruch gracza
    try:
        move_obj = board.parse_san(san_move)
        if move_obj not in board.legal_moves:
            logger.warning("Illegal move attempted.")
            return jsonify({"error": "Illegal move"}), 400
        board.push(move_obj)
        logger.info(f"Player moved: {san_move}")
    except Exception as e:
        logger.error(f"Error parsing player move: {e}")
        return jsonify({"error": str(e)}), 400

    # Sprawdź, czy gra się nie skończyła po ruchu gracza
    if board.is_game_over():
        move_history = get_move_history(board)
        logger.info("Game over after player's move.")
        return jsonify({
            "status": "gameover",
            "result": str(board.outcome()),
            "moveHistory": move_history,
            "lastMove": "",
            "fen": board.fen()
        })

    # 2. Ruch komputera (Stockfish)
    try:
        result = engine.play(board, limit=chess.engine.Limit(time=1))
        board.push(result.move)
        logger.info(f"Computer moved: {result.move}")
    except Exception as e:
        logger.error(f"Error with computer move: {e}")
        return jsonify({"error": f"Error with computer move: {str(e)}"}), 500

    # **Poprawka: Tymczasowo cofnij ostatni ruch, aby uzyskać SAN**
    try:
        last_move = board.pop()  # Cofnij ruch komputera
        comp_san = board.san(last_move)  # Uzyskaj SAN dla ruchu komputera
        board.push(last_move)  # Przywróć ruch komputera na planszę
        logger.info(f"Computer move SAN: {comp_san}")
    except Exception as e:
        logger.error(f"Error processing computer's move SAN: {e}")
        return jsonify({"error": f"Error processing computer's move SAN: {str(e)}"}), 500

    # Sprawdź, czy gra się nie skończyła po ruchu komputera
    if board.is_game_over():
        move_history = get_move_history(board)
        logger.info("Game over after computer's move.")
        return jsonify({
            "status": "gameover",
            "result": str(board.outcome()),
            "moveHistory": move_history,
            "lastMove": comp_san,
            "fen": board.fen()
        })

    # Generuj pełną historię ruchów
    move_history = get_move_history(board)
    logger.info(f"Move history to return: {move_history}")

    # Wyodrębnij ostatni ruch
    move_pairs = move_history.split(' ')
    last_move = move_pairs[-1] if move_pairs else ""

    # Zwracamy JSON z informacją o historii ruchów i stanie gry
    return jsonify({
        "status": "ok",
        "moveHistory": move_history,
        "lastMove": last_move,
        "fen": board.fen()
    })


@app.route("/undo", methods=["POST"])
def undo():
    """
    Cofamy dwa ruchy (gracza i komputera) lub jeden, jeśli grała tylko gracz.
    """
    global board

    logger.info("Undo requested.")

    if len(board.move_stack) >= 1:
        undone_move = board.pop()  # Cofnij ruch komputera
        logger.info(f"Undone move: {undone_move}")
    if len(board.move_stack) >= 1:
        undone_move = board.pop()  # Cofnij ruch gracza
        logger.info(f"Undone move: {undone_move}")

    # Generuj historię ruchów po cofnięciu
    move_history = get_move_history(board)
    logger.info(f"Move history after undo: {move_history}")

    return jsonify({
        "status": "ok",
        "fen": board.fen(),
        "moveHistory": move_history
    })

if __name__ == "__main__":
    try:
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=True)
    except Exception as e:
        logger.error(f"Error running Flask app: {e}")
