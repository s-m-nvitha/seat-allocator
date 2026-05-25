from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def times(number):
    """Returns a range of numbers from 0 to number-1."""
    return range(number)

@register.simple_tag
def get_seat(allocations, row, col):
    """Get seat allocation for a specific position."""
    for allocation in allocations:
        if allocation.row == row and allocation.column == col:
            return allocation
    return None 