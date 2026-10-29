def append(list1, list2):
    """Given two lists, add all items in the second list to the end of the first list."""
    result = []
    for item in list1:
        result.append(item)
    for item in list2:
        result.append(item)
    return result


def concat(lists):
    """Given a series of lists, combine all items in all lists into one flattened list."""
    result = []
    for lst in lists:
        for item in lst:
            result.append(item)
    return result


def filter(predicate, lst):
    """Given a predicate and a list, return the list of all items for which predicate(item) is True."""
    result = []
    for item in lst:
        if predicate(item):
            result.append(item)
    return result


def length(lst):
    """Given a list, return the total number of items within it."""
    count = 0
    for _ in lst:
        count += 1
    return count


def map(function, lst):
    """Given a function and a list, return the list of the results of applying function(item) on all items."""
    result = []
    for item in lst:
        result.append(function(item))
    return result


def foldl(function, lst, initial):
    """Given a function, a list, and initial accumulator, fold (reduce) each item into the accumulator from the left."""
    accumulator = initial
    for item in lst:
        accumulator = function(accumulator, item)
    return accumulator


def foldr(function, lst, initial):
    """Given a function, a list, and an initial accumulator, fold (reduce) each item into the accumulator from the right."""
    accumulator = initial
    for item in reversed(lst):
        accumulator = function(accumulator, item)
    return accumulator


def reverse(lst):
    """Given a list, return a list with all the original items, but in reversed order."""
    result = []
    for i in range(len(lst) - 1, -1, -1):
        result.append(lst[i])
    return result