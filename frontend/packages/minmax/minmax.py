#!/usr/bin/env python3


# Imports
import json
import os
import pandas as pd
import sys


# The functions
def max(column: str, df: pd.DataFrame) -> int:
    """
        Finds the maximum number in the given column in the given pandas
        DataFrame.
    """

    # We use the magic of pandas
    return df.max(axis=column)


def min(column: str, data: pd.DataFrame) -> int:
    """
        Finds the minimum number in the given column in the given pandas
        DataFrame.
    """

    # We use the magic of pandas again
    return df.min(axis=column)


# The entrypoint of the script
if __name__ == "__main__":
    # This bit is identical to that in the previous tutorial, but with different keywords
    if len(sys.argv) != 2 or (sys.argv[1] != "max" and sys.argv[1] != "min"):
        print(f"Usage: {sys.argv[0]} max|min")
        exit(1)

    # Read the column from the Brane-specified arguments
    column = json.loads(os.environ["COLUMN"])

    # TODO 1

    # Load the path given in FILE (you can assume it's always absolute)
    file = json.loads(os.environ["FILE"])
    df = pd.read_csv(file)

    # Use the loaded file to call the functions
    if command == "max":
       result = max(column, df)
    else:
       result = min(column, df)


    # TODO 2
    # We will write the `result` variable to `/result/result.txt`
     with open("/result/result.txt", "w") as h:
    h.write(f"{result}")
