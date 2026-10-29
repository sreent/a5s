"""Services: the scheduler, and context.

They change the trusted core's data only through the gateway, so a fault here
can make an agent slow, wrong or silent, but not do what policy denies.
"""
