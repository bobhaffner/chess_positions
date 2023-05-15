import requests
import json
import math
import chess, chess.engine, chess.pgn
from io import StringIO
import random

import numpy as np
from PIL import Image
import pyvips
from matplotlib import pyplot as plt
import matplotlib


def get_game_archives(player_name):

    # get game archives
    r = requests.get(f'https://api.chess.com/pub/player/{player_name}/games/archives')
    return json.loads(r.text)


def get_game_archive(archive_url):
    
    r = requests.get(archive_url)
    return json.loads(r.text)
    

def get_latest_game_archive(game_archives):

    return get_game_archive(game_archives['archives'][-1])


def get_pov(game, player_name):

    # are we playing white or black
    if game['white']['username'] == player_name:
        return chess.WHITE
    return chess.BLACK


player_name =  'bobhaffner'

game_archives = get_game_archives(player_name)

game_archive = get_latest_game_archive(game_archives)
print(f"{len(game_archive['games'])} games from {game_archives['archives'][-1]}")

game_info = game_archive['games'][-2]

pov = get_pov(game_info, player_name)

# any move that drop the eval by more than the goof_threshold will be put in the flash card pile
# lower goof_threshold = more flash cards
# higher goof_threshold = less flash cards
goof_threshold = 150

stockfish_path = '/opt/homebrew/Cellar/stockfish/15/bin/stockfish'

# create some python-chess objs    
# https://github.com/niklasf/python-chess
engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
game = chess.pgn.read_game(StringIO(game_info['pgn']))
board = game.board()
moves = game.mainline_moves()

# these next two will be keeping track of info from the prior move
# prior_eval = None
# engine_move = None
# engine_move_capture = None

# create a list to keep track of our goofs
goofs = []

# iterate thru each move and eval the position after each one
for i, move in enumerate(moves):
    
    if board.turn != pov:
        board.push(move)
        continue

    # what was played
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
        
        print(player_move, '--', engine_move_san, '\n')
        
        # create a dict to house goof metadata and svgs
        goof = {}
        goof['move_num'] = math.ceil((i + 1) / 2)
        goof['goof_factor'] = abs(before_move_eval - after_move_eval)
        goof['engine_move'] = engine_move 
        
        arrow_player_move = chess.svg.Arrow(move.from_square, move.to_square, color='red')
        goof['svg'] = chess.svg.board(board,
                                      arrows=[arrow_player_move], 
                                      orientation=pov, 
                                      size=500)
        goof['svg_with_engine_move'] = chess.svg.board(board,
                                                       arrows=[arrow_player_move, 
                                                               chess.svg.Arrow(engine_move.from_square, engine_move.to_square)], 
                                                       orientation=pov, 
                                                       size=500)
        goofs.append(goof)



engine.quit()

print(f'{len(goofs)} goof(s) this game')


# lets ease into this by sorting best to worst
sorted_goofs = sorted(goofs, key=lambda d: d['goof_factor']) 

format_to_dtype = {
    'uchar': np.uint8,
    'char': np.int8,
    'ushort': np.uint16,
    'short': np.int16,
    'uint': np.uint32,
    'int': np.int32,
    'float': np.float32,
    'double': np.float64,
    'complex': np.complex64,
    'dpcomplex': np.complex128,
}

fig = plt.figure(figsize=(20, 40))
rows = len(goofs)

for i, goof in zip(range(1, rows * 2 + 1, 2), sorted_goofs):
    
    img = pyvips.Image.svgload_buffer(str.encode(goof['svg']))
    data = np.ndarray(buffer=img.write_to_memory(), dtype=format_to_dtype[img.format],
                   shape=[img.height, img.width, img.bands])
    axl = fig.add_subplot(rows, 2, i)
    axl.set_title('FRONT')
    plt.imshow(img)
    
    img_with_engine_move = pyvips.Image.svgload_buffer(str.encode(goof['svg_with_engine_move']))
    data = np.ndarray(buffer=img.write_to_memory(), dtype=format_to_dtype[img.format],
                   shape=[img.height, img.width, img.bands])
    axl = fig.add_subplot(rows, 2, i + 1)
    axl.set_title('BACK')
    plt.imshow(img_with_engine_move)
    
plt.rcParams.update({'font.size': 22})
fig.tight_layout()
plt.savefig(f"images/flash_cards_{game_info['uuid']}.jpg")
#plt.show()