@echo off
echo pg_restore -d %1 -h localhost -U postgres -c %2
