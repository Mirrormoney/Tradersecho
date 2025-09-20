@echo off
echo pg_dump -Fc -d %1 -h localhost -U postgres -f %2
