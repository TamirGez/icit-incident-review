# Reversible ICIT_TEST_* setup for the assigned hackathon lab only.
# Read submission/REPRODUCE.md, create the three analytics events in the UI first.
[CmdletBinding()]
param([switch]$ApprovedTestSetup,
      [string]$ReportPath=(Join-Path $env:TEMP 'ICIT_TEST_setup_result.json'))
$ErrorActionPreference='Stop'
$OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$script:GatewaySession=$null
function Invoke-Gateway {
    param([string]$Method, [string]$Path, $Body = $null)
    if ($Path -notmatch '^/api/[A-Za-z0-9/?=&_.%-]+$') { throw 'Invalid gateway path' }
    $cfg = @('silent', 'show-error', 'fail', 'insecure', 'max-time = 30',
        ('url = "https://localhost:15443' + $Path + '"'),
        ('request = "' + $Method + '"'), 'header = "Content-Type: application/json"')
    if ($script:GatewaySession) { $cfg += 'header = "X-Session-Id: ' + $script:GatewaySession + '"' }
    if ($null -ne $Body) {
        $json = $Body | ConvertTo-Json -Depth 12 -Compress
        $escaped = $json.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n')
        $cfg += 'data-binary = "' + $escaped + '"'
    }
    $raw = ($cfg -join "`n") | & curl.exe --config - 2>$null
    if ($LASTEXITCODE -ne 0) { throw ('Gateway curl exit ' + $LASTEXITCODE) }
    if ($raw) { return (($raw -join "`n") | ConvertFrom-Json) }
}

try {
 if (!$ApprovedTestSetup) {throw 'Review and approve the TEST setup before execution'}
 if ($env:COMPUTERNAME -ine 'p042') {throw 'This reviewed setup is restricted to assigned p042'}
 Get-Service -DisplayName 'Milestone XProtect Management Server' | Out-Null
 Import-Module MilestonePSTools
 Connect-Vms -ServerAddress 'http://localhost' -AcceptEula | Out-Null
 $secret=Read-Host 'Gateway administrator password (secure input)' -AsSecureString
 $credential=New-Object System.Management.Automation.PSCredential('administrator',$secret)
 $login=Invoke-Gateway 'POST' '/api/Sessions/Login' @{Name='administrator';Password=$credential.GetNetworkCredential().Password}
 $script:GatewaySession=$login.Id;$secret=$null;$credential=$null;$login=$null
 if (!$script:GatewaySession) {throw 'No gateway session'}
 $options=Invoke-Gateway 'GET' '/api/Rules/Actions/TriggerAnalyticsEvent/Options'
 $template=Get-Content (Join-Path $PSScriptRoot '../config/native-rule.template.json') -Raw | ConvertFrom-Json
 $scenarios=@(
  @{Prefix='RAIL';Config='person_on_railway_tracks';Camera='person_on_railway_tracks';Keyword='RAIL_INTRUSION'},
  @{Prefix='GATE';Config='school_gate_break_in_night';Camera='school_gate_break_in_night';Keyword='GATE_INTERACTION'},
  @{Prefix='SIDEWALK';Config='blocked_sidewalk';Camera='escooter_left_across_sidewalk';Keyword='SIDEWALK_BLOCKED'}
 )
 $role=Get-VmsRole | Where-Object Name -eq 'ICIT_TEST_CONNECTOR'
 if (!$role) {
  New-VmsRole -Name 'ICIT_TEST_CONNECTOR' -Description 'Hackathon connector: three TEST cameras; no administration' -AllowSmartClientLogOn | Out-Null
  Clear-VmsCache
  $role=Get-VmsRole | Where-Object Name -eq 'ICIT_TEST_CONNECTOR'
 }
 $result=@{Status='configured';Scenarios=@();ManualChecks=@('Analytics enabled on existing port 9090','External Events: Read/Trigger only the three TEST request events','Alarm definitions use their matching cameras')}
 foreach ($item in $scenarios) {
  $prefix='ICIT_TEST_'+$item.Prefix
  if (!($options | Where-Object Id -eq ($prefix+'_REVIEW'))) {throw 'Create matching TEST analytics event in Management Client first'}
  $config=Get-Content (Join-Path $PSScriptRoot ('../config/'+$item.Config+'.example.json')) -Raw | ConvertFrom-Json
  $camera=@(Get-VmsCamera | Where-Object Name -eq $item.Camera)
  if ($camera.Count -ne 1) {throw 'Expected exactly one scenario camera'}
  $camera=$camera[0]
  $acl=Get-DeviceAcl -Camera $camera -Role $role
  $acl.SecurityAttributes.GENERIC_READ='True'
  $acl.SecurityAttributes.VIEW_LIVE='True'
  $acl.SecurityAttributes.PLAYBACK='True'
  $acl.SecurityAttributes.READ_BOOKMARKS='True'
  $acl | Set-DeviceAcl
  $event=Get-UserDefinedEvent | Where-Object Name -eq ($prefix+'_REQUEST')
  if (!$event) {Add-UserDefinedEvent -Name ($prefix+'_REQUEST') | Out-Null;Clear-VmsCache;$event=Get-UserDefinedEvent | Where-Object Name -eq ($prefix+'_REQUEST')}
  $prompt=@((Invoke-Gateway 'GET' ('/api/Prompts?Limit=25&SearchString='+$prefix+'_SUMMARY')).PageContent | Where-Object Title -eq ($prefix+'_SUMMARY'))
  if ($prompt.Count -eq 0) {$prompt=@(Invoke-Gateway 'POST' '/api/Prompts' @{Title=$prefix+'_SUMMARY';Text=$config.gateway_prompt})}
  if ($prompt.Count -ne 1 -or $prompt[0].Text -ne $config.gateway_prompt) {throw 'Existing TEST prompt differs; review instead of overwriting'}
  $address='https://p042:15443/api/WebHook/xprotect?Name='+$prefix+'_SUMMARY&PromptId='+$prompt[0].Id+'&AiModelId=traffic-general&CreateBookmark=yes&PreBuffer=20&PostBuffer=10&CameraId='+$camera.Id
  $webhook=Get-VmsWebhook | Where-Object Name -eq ($prefix+'_SUMMARY')
  if (!$webhook) {New-VmsWebhook -Name ($prefix+'_SUMMARY') -Address $address | Out-Null;Clear-VmsCache;$webhook=Get-VmsWebhook | Where-Object Name -eq ($prefix+'_SUMMARY')}
  if ($webhook.Address -ne $address) {throw 'Existing TEST webhook differs; review instead of overwriting'}
  $rule=Get-VmsRule | Where-Object DisplayName -eq ($prefix+'_TO_HAFNIA')
  if (!$rule) {
   $properties=@{}
   foreach ($p in $template.PSObject.Properties) {$properties[$p.Name]=$p.Value}
   $properties.Name=$prefix+'_TO_HAFNIA';$properties.StartEventType=$prefix+'_REQUEST'
   $properties['Start.MIPAction:e4852d57-f44e-4514-950b-15ed63908266.Items']=$webhook.Path
   New-VmsRule -Name $properties.Name -Properties $properties | Out-Null
   Clear-VmsCache
   $rule=Get-VmsRule | Where-Object DisplayName -eq ($prefix+'_TO_HAFNIA')
  }
  if (!$rule.EnableProperty.Enabled -or ($rule.Properties | Where-Object Key -eq 'StartEventType').Value -ne [string]$event.Id -or ($rule.Properties | Where-Object Key -eq 'Start.MIPAction:e4852d57-f44e-4514-950b-15ed63908266.Items').Value -ne $webhook.Path) {throw 'Existing TEST rule differs'}
  $gatewayRule=@((Invoke-Gateway 'GET' ('/api/Rules?Limit=25&SearchString='+$prefix+'_REVIEW')).PageContent | Where-Object Name -eq ($prefix+'_REVIEW'))
  if ($gatewayRule.Count -eq 0) {Invoke-Gateway 'POST' '/api/Rules' @{Name=$prefix+'_REVIEW';Description='Visual evidence for operator review. No automatic action.';PromptId=$prompt[0].Id;Triggers=@(@{TriggerText=$item.Keyword;RuleActionId='TriggerAnalyticsEvent';RuleActionData=$prefix+'_REVIEW'})} | Out-Null}
  elseif ($gatewayRule.Count -ne 1 -or $gatewayRule[0].PromptId -ne $prompt[0].Id -or @($gatewayRule[0].Triggers).Count -ne 1 -or $gatewayRule[0].Triggers[0].TriggerText -ne $item.Keyword -or $gatewayRule[0].Triggers[0].RuleActionData -ne ($prefix+'_REVIEW')) {throw 'Existing TEST gateway rule differs'}
  $alarm=Get-VmsAlarmDefinition | Where-Object Name -eq ($prefix+'_OPERATOR_REVIEW')
  if ($alarm -and (!$alarm.Enabled -or $alarm.SourceList -ne $camera.Path -or $alarm.EventType -ne $alarm.EventTypeValues[$prefix+'_REVIEW'])) {throw 'Existing TEST alarm differs'}
  $result.Scenarios+=@{Scenario=$item.Config;CameraId=[string]$camera.Id;RequestEventId=[string]$event.Id;PromptId=$prompt[0].Id;WebhookPath=$webhook.Path;AlarmPresent=[bool]$alarm}
 }
 Set-VmsRoleOverallSecurity -Role $role -SecurityNamespace 'Analytics Events' -Permissions @{GENERIC_READ='Allow'} | Out-Null
 Set-VmsRoleOverallSecurity -Role $role -SecurityNamespace 'Alarms' -Permissions @{GENERIC_READ='Allow'} | Out-Null
 $user=Get-VmsBasicUser | Where-Object Name -eq 'ICIT_TEST_CONNECTOR'
 if (!$user) {
  $secret=Read-Host 'New scoped TEST basic-user password (secure input)' -AsSecureString
  $user=New-VmsBasicUser -Name 'ICIT_TEST_CONNECTOR' -Password $secret
  $secret=$null
  Add-VmsRoleMember -Role $role -Sid $user.Sid | Out-Null
 }
 $report=$result | ConvertTo-Json -Depth 8
 $report | Out-File $ReportPath -Encoding utf8
 $report
} catch {
 @{Status='needs_review';ErrorLine=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json | Out-File $ReportPath -Encoding utf8
 Write-Error ('TEST setup stopped at line '+$_.InvocationInfo.ScriptLineNumber+'. Review the corresponding operation; no automatic destructive rollback.')
} finally {
 if ($script:GatewaySession) {try {Invoke-Gateway 'POST' '/api/Sessions/Logout' @{Id=$script:GatewaySession} | Out-Null} catch {}}
 $script:GatewaySession=$null
}
