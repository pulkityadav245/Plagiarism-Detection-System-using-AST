# plagiarized_v1.py
# Script for shape math
import math

def circle_size(rad):
    # This computes area for circles
    if rad < 0:
        return "Error: Negative radius"
    return math.pi * (rad ** 2)

def rect_space(a, b):
    # Multiplication of sides
    return a * b

def run_script():
    val = 5
    print(f"Area: {circle_size(val)}")
    
    side1, side2 = 10, 4
    print(f"Rectangle: {rect_space(side1, side2)}")

if __name__ == "__main__":
    run_script()