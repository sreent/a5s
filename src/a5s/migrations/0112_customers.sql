-- Erasing someone outside the directory, such as a customer who writes to a shared mailbox,
-- puts a stand-in for their address in each of a5s's texts that held it (core/customers.py;
-- round 15). The core may change those words, and nothing else of them.
grant update (text) on outbox, inbound to a5s_gateway;
grant update (content) on turns to a5s_gateway;
grant update (said) on answer_feedback to a5s_gateway;
