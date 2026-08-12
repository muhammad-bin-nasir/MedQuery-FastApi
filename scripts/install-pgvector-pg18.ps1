# Run this script as Administrator once to install pgvector for PostgreSQL 18.
# This only adds extension files; it does not modify existing databases.

$ErrorActionPreference = 'Stop'
$pg = 'C:\Program Files\PostgreSQL\18'
$zip = Join-Path $env:TEMP 'vector-pg18.zip'
$extract = Join-Path $env:TEMP 'vector-pg18'
$url = 'https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/0.8.5_18.4/vector.v0.8.5-pg18.zip'

Write-Host 'Downloading pgvector for PostgreSQL 18...'
Invoke-WebRequest -Uri $url -OutFile $zip
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $extract -Force

Write-Host 'Installing pgvector files into PostgreSQL 18...'
Copy-Item (Join-Path $extract 'lib\vector.dll') (Join-Path $pg 'lib\') -Force
Copy-Item (Join-Path $extract 'share\extension\*') (Join-Path $pg 'share\extension\') -Force
New-Item -ItemType Directory -Path (Join-Path $pg 'include\server\extension\vector') -Force | Out-Null
Copy-Item (Join-Path $extract 'include\server\extension\vector\*') (Join-Path $pg 'include\server\extension\vector\') -Force

Write-Host 'Restarting PostgreSQL 18 service...'
Restart-Service postgresql-x64-18

Write-Host 'Done. pgvector is installed for PostgreSQL 18.'
