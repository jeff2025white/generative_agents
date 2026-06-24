#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# python 3.10 compatibility monkey-patch for django 2.2
import collections
import collections.abc
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableMapping = collections.abc.MutableMapping
collections.Sequence = collections.abc.Sequence
collections.MutableSequence = collections.abc.MutableSequence



def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'frontend_server.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
