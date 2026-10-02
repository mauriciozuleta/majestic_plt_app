from itertools import permutations


def orientations(item):
    dims = item['l'], item['w'], item['h']
    return list(dict.fromkeys([dims, (dims[1], dims[0], dims[2])] if item['upright'] else permutations(dims)))


def fits_door(item, door):
    if door is None:
        return True
    s = sorted([item['l'], item['w'], item['h']])
    d = sorted([door.width, door.height])
    return s[0] <= d[0] and s[1] <= d[1]
