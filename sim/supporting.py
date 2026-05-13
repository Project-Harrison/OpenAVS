import string, random
from copy import deepcopy
from . import paths as _paths

import datetime

vesselTimeLocal = datetime.datetime.today()

schema = 'voyage_id, name, time, lat, long, course, speed, offset, interval'

def writeToDatabase(vessel):
    row = vessel.voyage +','+ vessel.name +','+ str(vessel.date) +','+ str(vessel.p1[0]) +','+\
          str(vessel.p1[1]) +','+ str(vessel.course) +','+ str(vessel.speed)
    with open(_paths.stream_path(), 'a') as write_obj:
        write_obj.write(row)
        write_obj.write('\n')
        pass

from csv import reader
# with open('database/stream', 'r') as read_obj:
#     csv_reader = reader(read_obj)
#     list_of_rows = list(csv_reader)
#     print(list_of_rows)
#     pass

def identifier(stringLength=8):
    lettersAndDigits = string.ascii_letters.upper() + string.digits
    return ''.join((random.choice(lettersAndDigits) for i in range(stringLength)))

def scramble(name, intensity):
    """
     :param: string, intensity (0 is completely scrambled)
     :return: scrambled name
     """
    scrambledName = ""
    pool = r"*&^@%#&@%#<><><,,,..//:'[{}'(-?(?:0|[1-9]\d*))(\.\d+)?([eE][-+]?\d+)?"
    for item in name:
        if random.randint(0, intensity) == 0:
            scrambledName += random.choice(pool)
        else:
            scrambledName += item
    return scrambledName

def segregate(bots):
    """
    :param: bot objects
    :return: a list of all in sight bots. the outcome is applied to the object attribute 'self.inSight'
    """
    for num, item in enumerate(bots):
        item.bots = bots
        out = deepcopy(bots)

        # Apply own bot
        item.ownBot = out.pop(num)

        # Other bots
        item.otherBots = out

        # All bots
        item.allBots = bots
