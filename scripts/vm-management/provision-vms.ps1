<#
.SYNOPSIS
    Provision Kubernetes cluster VMs from template snapshot using VMware Workstation
    
.DESCRIPTION
    Stage 2.2: VM Provisioning via PowerShell + vmrun.exe
    - Clones 3 VMs (1 master, 2 workers) from template snapshot
    - Configures hardware specifications (CPU, RAM)
    - Powers on VMs and waits for network initialization
    - Generates Ansible inventory with DHCP IPs
    
.NOTES
    Author: Shalev (DevOps Homelab Project)
    Date: 2026-01-10
    Replaces: Terraform (abandoned due to provider bugs - see ADR-005)
#>

#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [switch]$WhatIf,
    [switch]$Force
)

# ================================================================================
# CONFIGURATION
# ================================================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# Paths
$vmrunPath = "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
$templateVMX = "D:\homelab\vms\templates\k8s-template\k8s-template.vmx"
$snapshotName = "Clean Template - DHCP Bootstrap v2"
$clusterDir = "D:\homelab\vms\cluster"
$inventoryPath = "D:\homelab\ansible\inventory\hosts.ini"

# VM Specifications
$vms = @(
    @{
        Name = "k8s-master-01"
        CPU = 4
        RAM = 16384  # 16GB - Control plane needs more resources
        PlannedIP = "192.168.70.10"
        Role = "master"
    },
    @{
        Name = "k8s-worker-01"
        CPU = 4
        RAM = 12288  # 12GB - Optimized for homelab constraints
        PlannedIP = "192.168.70.11"
        Role = "worker"
    },
    @{
        Name = "k8s-worker-02"
        CPU = 4
        RAM = 12288  # 12GB - Symmetric with worker-01
        PlannedIP = "192.168.70.12"
        Role = "worker"
    }
)

# ================================================================================
# HELPER FUNCTIONS
# ================================================================================

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "INFO"    { "White" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR"   { "Red" }
        default   { "White" }
    }
    
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

function Test-Prerequisites {
    Write-Log "Checking prerequisites..."
    
    if (-not (Test-Path $vmrunPath)) {
        throw "vmrun.exe not found at: $vmrunPath"
    }
    
    if (-not (Test-Path $templateVMX)) {
        throw "Template VM not found at: $templateVMX"
    }
    
    # Get all snapshots
    $snapshotOutput = & $vmrunPath listSnapshots $templateVMX 2>&1 | Out-String
    
    # Parse snapshot names (skip "Total snapshots: X" line)
    $availableSnapshots = $snapshotOutput -split "`r?`n" | 
        Select-Object -Skip 1 | 
        Where-Object { $_ -and $_.Trim() -ne "" } |
        ForEach-Object { $_.Trim() }
    
    # Check if snapshot exists using exact string match (not regex)
    $snapshotFound = $false
    foreach ($snap in $availableSnapshots) {
        if ($snap -eq $snapshotName) {
            $snapshotFound = $true
            break
        }
    }
    
    if (-not $snapshotFound) {
        Write-Log "Available snapshots:" "ERROR"
        foreach ($snap in $availableSnapshots) {
            Write-Log "  - '$snap'" "ERROR"
        }
        throw "Snapshot '$snapshotName' not found in template VM"
    }
    
    if (-not (Test-Path $clusterDir)) {
        New-Item -ItemType Directory -Path $clusterDir -Force | Out-Null
    }
    
    $inventoryDir = Split-Path -Parent $inventoryPath
    if (-not (Test-Path $inventoryDir)) {
        New-Item -ItemType Directory -Path $inventoryDir -Force | Out-Null
    }
    
    Write-Log "All prerequisites satisfied" "SUCCESS"
}

function New-ClusterVM {
    param([hashtable]$VMConfig)
    
    $vmName = $VMConfig.Name
    $vmDir = Join-Path $clusterDir $vmName
    $vmxPath = Join-Path $vmDir "$vmName.vmx"
    
    Write-Log "Cloning VM: $vmName" "INFO"
    
    if (Test-Path $vmDir) {
        if ($Force) {
            Write-Log "Force mode: Removing existing VM directory" "WARNING"
            Remove-Item -Path $vmDir -Recurse -Force
        } else {
            throw "VM directory already exists: $vmDir (use -Force to overwrite)"
        }
    }
    
    New-Item -ItemType Directory -Path $vmDir -Force | Out-Null
    
    if ($WhatIf) {
        Write-Log "WHATIF: Would clone $vmName from snapshot" "WARNING"
        return $null
    }
    
    Write-Log "  Creating linked clone from snapshot: $snapshotName"
    $cloneResult = & $vmrunPath clone $templateVMX $vmxPath linked -snapshot="$snapshotName" -cloneName="$vmName" 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        throw "Clone failed for $vmName : $cloneResult"
    }
    
    Write-Log "  Clone created successfully" "SUCCESS"
    
    Write-Log "  Configuring hardware: $($VMConfig.CPU) vCPU, $($VMConfig.RAM)MB RAM"
    
    $vmxContent = Get-Content $vmxPath
    
    $vmxContent = $vmxContent | ForEach-Object {
        if ($_ -match '^numvcpus\s*=') {
            "numvcpus = `"$($VMConfig.CPU)`""
        } elseif ($_ -match '^cpuid.coresPerSocket\s*=') {
            "cpuid.coresPerSocket = `"$($VMConfig.CPU)`""
        } else {
            $_
        }
    }
    
    $vmxContent = $vmxContent | ForEach-Object {
        if ($_ -match '^memsize\s*=') {
            "memsize = `"$($VMConfig.RAM)`""
        } else {
            $_
        }
    }
    
    Set-Content -Path $vmxPath -Value $vmxContent
    
    Write-Log "  Hardware configured" "SUCCESS"
    
    return $vmxPath
}

function Start-ClusterVM {
    param([string]$VMXPath, [string]$VMName)
    
    Write-Log "Starting VM: $VMName" "INFO"
    
    if ($WhatIf) {
        Write-Log "WHATIF: Would start $VMName" "WARNING"
        return
    }
    
    $startResult = & $vmrunPath start $VMXPath nogui 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start $VMName : $startResult"
    }
    
    Write-Log "  VM started" "SUCCESS"
}

function Wait-VMNetwork {
    param([string]$VMXPath, [string]$VMName, [int]$TimeoutSeconds = 180)
    
    Write-Log "Waiting for $VMName to acquire IP address..." "INFO"
    
    if ($WhatIf) {
        Write-Log "WHATIF: Would wait for IP on $VMName" "WARNING"
        return "192.168.70.999"
    }
    
    $elapsed = 0
    $interval = 5
    
    while ($elapsed -lt $TimeoutSeconds) {
        Start-Sleep -Seconds $interval
        $elapsed += $interval
        
        $ipResult = & $vmrunPath getGuestIPAddress $VMXPath -wait 2>&1
        
        if ($LASTEXITCODE -eq 0 -and $ipResult -match '^\d+\.\d+\.\d+\.\d+$') {
            Write-Log "  IP acquired: $ipResult" "SUCCESS"
            return $ipResult
        }
        
        Write-Host "." -NoNewline
    }
    
    throw "Timeout: $VMName did not acquire IP within $TimeoutSeconds seconds"
}

function New-AnsibleInventory {
    param([array]$VMDetails)
    
    Write-Log "Generating Ansible inventory: $inventoryPath" "INFO"
    
    if ($WhatIf) {
        Write-Log "WHATIF: Would generate inventory file" "WARNING"
        return
    }
    
    $inventoryLines = @()
    
    $inventoryLines += "# Ansible Inventory - Kubernetes Homelab"
    $inventoryLines += "# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    $inventoryLines += "# Stage 2.2: Initial provisioning with DHCP IPs"
    $inventoryLines += "# NOTE: These IPs will be replaced with static assignments in Stage 2.3"
    $inventoryLines += ""
    $inventoryLines += "[all:vars]"
    $inventoryLines += "ansible_user=k8s"
    $inventoryLines += "ansible_ssh_private_key_file=~/.ssh/homelab_ed25519"
    $inventoryLines += "ansible_python_interpreter=/usr/bin/python3"
    $inventoryLines += ""
    $inventoryLines += "# ============================================================================"
    $inventoryLines += "# CONTROL PLANE"
    $inventoryLines += "# ============================================================================"
    $inventoryLines += "[masters]"
    
    foreach ($vm in $VMDetails | Where-Object { $_.Role -eq "master" }) {
        $inventoryLines += "$($vm.Name) ansible_host=$($vm.CurrentIP) planned_static_ip=$($vm.PlannedIP)"
    }
    
    $inventoryLines += ""
    $inventoryLines += "# ============================================================================"
    $inventoryLines += "# WORKER NODES"
    $inventoryLines += "# ============================================================================"
    $inventoryLines += "[workers]"
    
    foreach ($vm in $VMDetails | Where-Object { $_.Role -eq "worker" }) {
        $inventoryLines += "$($vm.Name) ansible_host=$($vm.CurrentIP) planned_static_ip=$($vm.PlannedIP)"
    }
    
    $inventoryLines += ""
    $inventoryLines += "# ============================================================================"
    $inventoryLines += "# CLUSTER GROUPING"
    $inventoryLines += "# ============================================================================"
    $inventoryLines += "[k8s_cluster:children]"
    $inventoryLines += "masters"
    $inventoryLines += "workers"
    $inventoryLines += ""
    
    $inventory = $inventoryLines -join "`n"
    Set-Content -Path $inventoryPath -Value $inventory
    
    Write-Log "  Inventory written successfully" "SUCCESS"
}

# ================================================================================
# MAIN EXECUTION
# ================================================================================

try {
    Write-Log "========================================" "INFO"
    Write-Log "Stage 2.2: VM Provisioning" "INFO"
    Write-Log "========================================" "INFO"
    
    if ($WhatIf) {
        Write-Log "Running in WHATIF mode - no changes will be made" "WARNING"
    }
    
    Test-Prerequisites
    
    Write-Log "" "INFO"
    Write-Log "Phase 1: Cloning VMs from template snapshot" "INFO"
    $vmxPaths = @{}
    foreach ($vm in $vms) {
        $vmxPath = New-ClusterVM -VMConfig $vm
        if ($vmxPath) {
            $vmxPaths[$vm.Name] = $vmxPath
        }
    }
    
    Write-Log "" "INFO"
    Write-Log "Phase 2: Starting VMs" "INFO"
    $sortedVMs = $vms | Sort-Object { if ($_.Role -eq "master") { 0 } else { 1 } }
    
    foreach ($vm in $sortedVMs) {
        if ($vmxPaths.ContainsKey($vm.Name)) {
            Start-ClusterVM -VMXPath $vmxPaths[$vm.Name] -VMName $vm.Name
            Start-Sleep -Seconds 10
        }
    }
    
    Write-Log "" "INFO"
    Write-Log "Phase 3: Waiting for network initialization" "INFO"
    $vmDetails = @()
    
    foreach ($vm in $vms) {
        if ($vmxPaths.ContainsKey($vm.Name)) {
            $currentIP = Wait-VMNetwork -VMXPath $vmxPaths[$vm.Name] -VMName $vm.Name
            
            $vmDetails += @{
                Name = $vm.Name
                Role = $vm.Role
                CurrentIP = $currentIP
                PlannedIP = $vm.PlannedIP
            }
        }
    }
    
    Write-Log "" "INFO"
    Write-Log "Phase 4: Generating Ansible inventory" "INFO"
    New-AnsibleInventory -VMDetails $vmDetails
    
    Write-Log "" "SUCCESS"
    Write-Log "========================================" "SUCCESS"
    Write-Log "Provisioning Complete!" "SUCCESS"
    Write-Log "========================================" "SUCCESS"
    Write-Log "" "INFO"
    Write-Log "VM Details:" "INFO"
    
    foreach ($vm in $vmDetails) {
        Write-Log "  $($vm.Name): $($vm.CurrentIP) -> $($vm.PlannedIP) (planned)" "INFO"
    }
    
    Write-Log "" "INFO"
    Write-Log "Next Steps:" "INFO"
    Write-Log "  1. Test Ansible connectivity: ansible all -i ansible/inventory/hosts.ini -m ping" "INFO"
    Write-Log "  2. Proceed to Stage 2.3: Static IP configuration via Ansible" "INFO"
    
} catch {
    Write-Log "ERROR: $_" "ERROR"
    Write-Log $_.ScriptStackTrace "ERROR"
    exit 1
}
