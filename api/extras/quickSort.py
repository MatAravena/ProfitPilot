import random

def QuickSort(list):
    quick_sort2(list, 0, len(list)-1)

def quick_sort2(list, low, hi):
    if low < hi:
        p = partition(list, low, hi)
        quick_sort2(list, low, p -1)
        quick_sort2(list, p +1, hi)

def get_pivot(list, low, hi):
    mid = (hi + low) // 2
    pivot = hi

    if list[low] < list[mid]:
        if list[low] < list[mid]:
            pivot = mid
    elif list[low] < list[hi]:
        pivot = low
    return pivot

def partition(list, low, hi):
    pivotIndex = get_pivot(list, low,  hi)
    pivotValue = list[pivotIndex]
    list[pivotIndex], list[low] = list[low], list[pivotIndex]
    border = low

    for i in range(low, hi+1):
        if list[i] < pivotValue:
            border +=1
            list[i], list[border] = list[i], list[border]

    list[low], list[border] = list[border], list[low]
    return border

def quick_sort(arr):
    if len(arr) <= 1:
        return arr

    # Use the last element as the pivot
    pivot = arr[-1]
    left = [x for x in arr[:-1] if x < pivot]
    right = [x for x in arr[:-1] if x >= pivot]

    # Recursively sort the left and right partitions and concatenate with pivot
    return quick_sort(left) + [pivot] + quick_sort(right)

def quick_sort_unique(n, unsorted_array):
    # Step 1: Sort the array
    sorted_array = quick_sort(unsorted_array)
    # Step 2: Remove duplicates by converting the list to a set and back to a sorted list
    unique_sorted_array = sorted(set(sorted_array))
    # Get the length of the sorted, unique array
    m = len(unique_sorted_array)
    return m, unique_sorted_array

# Test the function with the examples
example_1 = [3, 1, 2]
example_2 = [2, 2, 2, 3, 1]

# Running the test cases
# print(quick_sort_unique(3, example_1))  # Expected output: (3, [1, 2, 3])
# print(quick_sort_unique(5, example_2))  # Expected output: (3, [1, 2, 3])

randomList = random.sample(range(-20, 50), 15)
# print(quick_sort(randomList))
print(QuickSort(randomList))


def mineQuickSort(length, list):
    #pivot = (length - 1) // 2
    pivot = list[-1]

    left_list = list[:pivot]
    right_list = list[pivot:]

def uniqueSorted(list):
    newList = []

    for i in range(0, len(list)-1):
        if i == 0:
            newList.append(list[i])
        elif newList[i-1] != list[i]:
            newList.append(list[i])
    return newList

mineQuickSort(len(randomList), randomList)
