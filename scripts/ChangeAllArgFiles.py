import sys
import glob
import os
import ntpath


def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


if __name__ == "__main__":
    """
    takes two arguments: n, data
    n: int of the line to edit (starting at 1)
    data: the data you wish to replace on line n for all arg files
    """
    for path in glob.glob(os.getcwd() + "/*.txt"):
        filename = path_leaf(path)
        if filename[:5] != "args_" or filename == "args_reference.txt":
            continue
        with open(path, 'r') as file:
            data = file.readlines()

        with open(path, 'w') as file:
            for i, line in enumerate(data, 1):
                if i == int(sys.argv[1]):
                    file.writelines(sys.argv[2] + "\n")
                else:
                    file.writelines(line)
