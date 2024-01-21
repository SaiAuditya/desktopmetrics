tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    set windowTitle to name of first window of (first application process whose name is frontApp)
end tell

if frontApp is "Google Chrome" then
    tell application "Google Chrome"
        set frontmostTab to active tab of front window
        set tabURL to URL of frontmostTab
    end tell
    set tabDomain to do shell script "echo '" & tabURL & "' | awk -F/ '{print $3}'"
else if frontApp is "Safari" then
    tell application "Safari"
        set frontmostTab to current tab of front window
        set tabURL to URL of frontmostTab
    end tell
    set tabDomain to do shell script "echo '" & tabURL & "' | awk -F/ '{print $3}'"
else
    set tabURL to "Not Web"
    set tabDomain to "Not Web"
end if

return frontApp & " --- " & windowTitle & " --- " & tabURL & " --- " & tabDomain
