import requests
import json
import math
import chess, chess.engine, chess.pgn
from io import StringIO
import numpy as np
from PIL import Image
import pyvips
import csv
import argparse
import uuid


def main(player_name, goof_threshold, pgn_path, stockfish_path, card_images_path):

    # create a random id for this run
    run_id = str(uuid.uuid4())

    games = get_pgn(pgn_path)

    print(f'{len(games)} games in {pgn_path}')

    engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)

    # create a list to keep track of our goofs
    goofs = []

    for game in games:
        
        # create random id for this game
        game_id = str(uuid.uuid4())

        # did we play white or black
        pov = get_pov(game, player_name)

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
            
            # what we played
            player_move = board.san(move)

            before_move_info = engine.analyse(board, limit=chess.engine.Limit(time=.1))
            engine_move = before_move_info['pv'][0] if 'pv' in before_move_info else None
            engine_move_san = board.san(engine_move)

            before_move_eval = before_move_info["score"].pov(pov).score(mate_score=100000)
            
            board.push(move)

            after_move_info = engine.analyse(board, limit=chess.engine.Limit(time=.1))
            after_move_eval = after_move_info["score"].pov(pov).score(mate_score=100000)

            # was this move a goof
            if after_move_eval < before_move_eval and abs(before_move_eval - after_move_eval) >= goof_threshold:
                
                print(f'Went {player_move} but should have gone {engine_move_san}\n')
                
                # create a dict to house goof metadata and svgs
                goof = {}
                goof['move_num'] = math.ceil((i + 1) / 2)
                goof['goof_factor'] = abs(before_move_eval - after_move_eval)
                goof['engine_move'] = engine_move
                goof['card_id'] = f'{run_id}_{game_id}'
        
                arrow_player_move = chess.svg.Arrow(move.from_square, move.to_square, color='red')
                goof['svg'] = chess.svg.board(before_board,
                                            arrows=[arrow_player_move], 
                                            orientation=pov, 
                                            size=500)
            
                goof['svg_with_engine_move'] = chess.svg.board(before_board,
                                                            arrows=[arrow_player_move, 
                                                                    chess.svg.Arrow(engine_move.from_square, engine_move.to_square)], 
                                                            orientation=pov, 
                                                            size=500)
                goofs.append(goof)

    engine.quit()

    print(f'Found {len(goofs)} goof(s) in {pgn_path}')

    img_names = []
    
    for goof in goofs:
        
        front_img = svg_to_image(goof['svg'])
        front_img_name = f"{goof['card_id']}_{goof['move_num']}_front.jpg"
        front_img.save(f"{card_images_path}/{front_img_name}")

        front_img_csv_path = f"<img src='{front_img_name}'/>"

        back_img = svg_to_image(goof['svg_with_engine_move'])
        back_img_name = f"{goof['card_id']}_{goof['move_num']}_back.jpg"
        back_img.save(f"{card_images_path}/{back_img_name}")

        back_img_csv_path = f"<img src='{back_img_name}'/>"

        img_names.append((front_img_csv_path, back_img_csv_path))
        

    with open(f'csv/{run_id}_flash_cards.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(img_names)


def get_game_archives(player_name):

    # get game archives
    r = requests.get(f'https://api.chess.com/pub/player/{player_name}/games/archives')
    return json.loads(r.text)


def get_game_archive(archive_url):
    
    r = requests.get(archive_url)
    return json.loads(r.text)
    

def get_latest_game_archive(game_archives):

    return get_game_archive(game_archives['archives'][-1])


def get_latest_chess_com_game(player_name):

    # get all the game archives
    game_archives = get_game_archives(player_name)

    # get the latest games archive
    game_archive = get_latest_game_archive(game_archives)
    print(f"{len(game_archive['games'])} games from {game_archives['archives'][-1]}")

    # get a game
    game_info = game_archive['games'][-1]

    return chess.pgn.read_game(StringIO(game_info['pgn']))


def get_pgn(pgn_path):

    pgn = open(pgn_path)

    games = []

    while True:
        game = chess.pgn.read_game(pgn)
        if game is None:
            break  # end of file

        games.append(game)

    return games


def get_pov(game, player_name):

    # are we playing white or black
    if game.headers['White']== player_name:
        return chess.WHITE
    return chess.BLACK


def svg_to_image(svg):
    
    format_to_dtype = {'uchar': np.uint8}

    img = pyvips.Image.svgload_buffer(str.encode(svg))
    a = np.ndarray(buffer=img.write_to_memory(), dtype=format_to_dtype[img.format],
                   shape=[img.height, img.width, img.bands])
    
    im = Image.fromarray(a)
    return im.convert('RGB')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--player_name', dest='player_name', type=str, default='bobhaffner')
    parser.add_argument('--goof_threshold', dest='goof_threshold', type=int, default=150, 
                        help='Any move that drop the eval by more than the goof_threshold will be put in the flash card pile')
    
    parser.add_argument('--pgn_path', dest='pgn_path', type=str, 
                        default='pgn/chess_com_games_2023-05-16.pgn')
    # 'pgn/lichess_bobhaffner_2023-05-16.pgn'

    parser.add_argument('--stockfish_path', dest='stockfish_path', type=str, 
                        default='/opt/homebrew/Cellar/stockfish/15/bin/stockfish')
    parser.add_argument('--card_images_path', dest='card_images_path', type=str, 
                        default='/Users/bob/Library/Application Support/Anki2/User 1/collection.media')

    args = parser.parse_args()
    main(args.player_name, args.goof_threshold, args.pgn_path, args.stockfish_path, args.card_images_path)