import math
import chess, chess.engine, chess.pgn
import numpy as np
from PIL import Image
import pyvips
import csv
import argparse
import uuid
from pathlib import Path
from typing import List, Dict, TextIO, Any, Optional, Tuple

Game = chess.pgn.Game
Engine = chess.engine.SimpleEngine
InfoDict = chess.engine.InfoDict


def main(
    player_name: str,
    goof_threshold: int,
    pgn_path: str,
    stockfish_path: str,
    card_images_path: str,
    card_csv_path: str,
):
    games: List[Game] = get_pgn(pgn_path)

    print(f"Found {len(games)} games in {pgn_path}\n")

    engine = Engine.popen_uci(stockfish_path)

    # create a list to keep track of our goofs
    goofs: List[Dict] = []

    for game in games:
        # create id for this game
        game_id: str = f"{game.headers['Date'].replace('.', '_')}_{game.headers['White']}_{game.headers['Black']}_{str(uuid.uuid4())}"

        # did we play white or black
        pov: bool = get_pov(game, player_name)

        board = game.board()
        moves = game.mainline_moves()

        # iterate thru each move and eval the position after each one
        for i, move in enumerate(moves):
            # skip this move if it isn't ours
            if board.turn != pov:
                board.push(move)
                continue

            # get a copy of the board before any moves are played
            before_board = board.copy()

            before_board.board_fen()

            # what we played
            player_move: str = board.san(move)

            before_move_info: InfoDict = engine.analyse(
                board, limit=chess.engine.Limit(time=0.1)
            )
            engine_move: Optional[chess.Move] = (
                before_move_info["pv"][0] if "pv" in before_move_info else None
            )

            before_move_eval: int = (
                before_move_info["score"].pov(pov).score(mate_score=100000)
            )

            before_move_score: chess.engine.Score = before_move_info["score"].pov(pov)

            board.push(move)

            after_move_info: InfoDict = engine.analyse(
                board, limit=chess.engine.Limit(time=0.1)
            )
            after_move_eval: int = (
                after_move_info["score"].pov(pov).score(mate_score=100000)
            )

            # was this move a goof
            if (
                after_move_eval < before_move_eval
                and abs(before_move_eval - after_move_eval) >= goof_threshold
            ):
                # create a dict to house goof metadata and svgs
                goof: Dict[str, Any] = {}
                goof["move_num"] = math.ceil((i + 1) / 2)
                goof["goof_factor"] = abs(before_move_eval - after_move_eval)
                goof["engine_move"] = engine_move
                goof["engine_score"] = before_move_score
                goof["card_id"] = game_id
                goof[
                    "fen_url"
                ] = f"""<a href="https://lichess.org/analysis/fromPosition/{before_board.fen()}">Lichess Analysis Board</a>"""

                print(
                    f"{goof['card_id']}: {goof['move_num']}.{player_move} was a goof\n"
                )

                arrow_player_move: chess.svg.Arrow = chess.svg.Arrow(
                    move.from_square, move.to_square, color="red"
                )
                goof["svg"] = chess.svg.board(
                    before_board, arrows=[arrow_player_move], orientation=pov, size=500
                )

                from_square: int = 0 if not engine_move else engine_move.from_square
                to_square: int = 0 if not engine_move else engine_move.to_square

                goof["svg_with_engine_move"] = chess.svg.board(
                    before_board,
                    arrows=[
                        arrow_player_move,
                        chess.svg.Arrow(from_square, to_square),
                    ],
                    orientation=pov,
                    size=500,
                )
                goofs.append(goof)

    engine.quit()

    print(f"Found {len(goofs)} goof(s) in {pgn_path}")

    img_names: List[Tuple[str, str]] = []

    # create output folders if needed
    Path(card_images_path).mkdir(parents=True, exist_ok=True)

    p = Path(card_csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    for goof in goofs:
        front_img: Image = svg_to_image(goof["svg"])
        front_img_name: str = f"{goof['card_id']}_{goof['move_num']}_front.jpg"
        front_img.save(f"{card_images_path}/{front_img_name}")

        front_img_csv_path: str = f"""<img src='{front_img_name}'/><p><br>{game.headers['Date']} 
                                {game.headers['White']} vs {game.headers['Black']} on move {goof['move_num']} {goof["fen_url"]} </p>"""

        back_img: Image = svg_to_image(goof["svg_with_engine_move"])
        back_img_name: str = f"{goof['card_id']}_{goof['move_num']}_back.jpg"
        back_img.save(f"{card_images_path}/{back_img_name}")

        back_img_csv_path: str = f"<img src='{back_img_name}'/>"

        img_names.append((front_img_csv_path, back_img_csv_path))

    with open(card_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(img_names)


def get_pgn(pgn_path: str) -> List[Game]:
    pgn: TextIO = open(pgn_path)

    games: List[Game] = []

    while True:
        game = chess.pgn.read_game(pgn)
        if game is None:
            break  # end of file

        games.append(game)

    return games


def get_pov(game: Game, player_name: str) -> bool:
    # are we playing white or black
    if game.headers["White"] == player_name:
        return chess.WHITE
    return chess.BLACK


def svg_to_image(svg: str) -> Image:
    format_to_dtype: Dict[str, type] = {"uchar": np.uint8}

    img: Image = pyvips.Image.svgload_buffer(str.encode(svg))
    a: np.ndarray = np.ndarray(
        buffer=img.write_to_memory(),
        dtype=format_to_dtype[img.format],
        shape=[img.height, img.width, img.bands],
    )

    im: Image = Image.fromarray(a)
    return im.convert("RGB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--player_name", dest="player_name", type=str, default="bobhaffner"
    )
    parser.add_argument(
        "--goof_threshold",
        dest="goof_threshold",
        type=int,
        default=150,
        help="Any move that drop the eval by more than the goof_threshold will be put in the flash card pile",
    )

    parser.add_argument(
        "--pgn_path",
        dest="pgn_path",
        type=str,
        default="pgn/chess_com_games_2023-05-16.pgn",
        help="Path of the pgn",
    )
    # 'pgn/lichess_bobhaffner_2023-05-16.pgn'

    parser.add_argument(
        "--stockfish_path",
        dest="stockfish_path",
        type=str,
        default="/opt/homebrew/Cellar/stockfish/15.1/bin/stockfish",
        help="Stockfish location",
    )
    parser.add_argument(
        "--card_images_path",
        dest="card_images_path",
        type=str,
        default="/Users/bob/Library/Application Support/Anki2/User 1/collection.media",
        help="The desired exported images location",
    )
    parser.add_argument(
        "--card_csv_path",
        dest="card_csv_path",
        type=str,
        default="csv/flash_cards.csv",
        help="The desired exported csv location to be used in the Anki import",
    )

    args = parser.parse_args()
    main(
        args.player_name,
        args.goof_threshold,
        args.pgn_path,
        args.stockfish_path,
        args.card_images_path,
        args.card_csv_path,
    )
