$lines = Get-Content 'code.txt'
$headers = @()
for ($i=0; $i -lt ($lines.Length - 2); $i++) {
    if ($lines[$i+2].Trim() -ceq 'Copy') {
        $lang = $lines[$i+1].Trim().ToLower()
        $validLangs = @('txt', 'python', 'dockerfile', 'yaml', 'yml', 'json', 'tsx', 'ts', 'typescript', 'bash', 'sh', 'javascript', 'js', 'sql')
        if ($validLangs -contains $lang) {
            $filepathLine = $lines[$i].Trim()
            $filepath = $filepathLine -split ' - '
            $filepath = $filepath[0].Trim()
            if ($filepath -notmatch '^1\. Production') {
                $headers += [PSCustomObject]@{
                    Index = $i
                    FilePath = $filepath
                    Lang = $lang
                }
            }
        }
    }
}

# Now extract the content and write files
$baseDir = "d:\dsA_I\ai-hos"
if (-not (Test-Path $baseDir)) {
    New-Item -ItemType Directory -Path $baseDir | Out-Null
}

for ($idx = 0; $idx -lt $headers.Count; $idx++) {
    $h = $headers[$idx]
    
    $startLine = $h.Index + 3
    if ($idx -lt $headers.Count - 1) {
        $endLine = $headers[$idx+1].Index - 1
    } else {
        $endLine = $lines.Length - 1
    }
    
    # Backtrack endLine to ignore empty lines or non-code text from the next section header
    while ($endLine -ge $startLine -and $lines[$endLine].Trim() -eq '') {
        $endLine--
    }
    
    # Heuristic: the last line might be normal text if it's not starting with a code-like indent or if it's followed by "Service 2..." etc.
    # Actually, we can just grab everything up to endLine. Text outside code blocks might cause syntax errors in python.
    # Let's inspect the lines right before start of next file.
    # If the lines prior don't look like code, we'll see. Often they are clear text. Let's just output and we can fix them.
    # Wait, we know from earlier that there are text like "Service 2: Prior Authorization Engine".
    # I'll check if the line starts with "Service " or "Phase" or something similarly descriptive and ignore it from the end.
    while ($endLine -ge $startLine) {
        $lastLine = $lines[$endLine]
        if ($lastLine -match '^Service \d+:' -or $lastLine -match 'This is your flagship service' -or $lastLine -match '^2\. Phase 1 MVP') {
            $endLine--
        } else {
            break
        }
    }

    # Also back out empty lines again
    while ($endLine -ge $startLine -and $lines[$endLine].Trim() -eq '') {
        $endLine--
    }

    $content = @()
    if ($startLine -le $endLine) {
        for ($j = $startLine; $j -le $endLine; $j++) {
            $content += $lines[$j]
        }
    }
    
    $fullPath = Join-Path $baseDir $h.FilePath
    Write-Host "Creating file $fullPath"
    
    $dir = Split-Path $fullPath
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    
    [System.IO.File]::WriteAllLines($fullPath, $content)
}

Write-Host "Done parsing and writing code files!"
