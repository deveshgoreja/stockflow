-- Runs once, when the Postgres volume is first created, so `pytest` can use the
-- Compose database server without any manual setup.
CREATE DATABASE stockflow_test;
