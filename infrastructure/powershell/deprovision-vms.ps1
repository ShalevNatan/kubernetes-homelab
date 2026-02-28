<#
.SYNOPSIS
    Deprovision Kubernetes cluster VMs and cleanup associated resources
    
.DESCRIPTION
    Stage 2.2: VM Deprovisioning (companion to provision-vms.ps1)
    - Safely shuts down VMs
    - Deletes VM directories
    - Optionally removes Ansible inventory
    - Provides rollback capability for testing/iteration
    
.PARAMETER KeepInventory
    Preserve ansible/inventory/hosts.ini file (useful for documentation)
    
.PARAMETER Force
    Skip confirmation prompts
    
.EXAMPLE
    .\deprovision-vms.ps1
    # Interactive mode with confirmations
    
.EXAMPLE
    .\deprovision-vms.ps1 -Force
    # Immediate cleanup without prompts
    
.EXAMPLE
    .\deprovision-vms.ps1 -KeepInventory
    # Remove VMs but preserve inventory file for reference
    
.NOTES
    Author: Shalev (DevOps Homelab Project)
    Date: 2026-01-10
    Pairs with: provision-vms.ps1
#>

#Requires -RunAsAdministrator

[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$KeepInventory,
    [switch]$Force
)

# ================================================================================
# CONFIGURATION
# ================================================================================

$ErrorActionPreference = "Stop"

# Paths
$vmrunPath = "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
$clusterDir = "D:\homelab\vms\cluster"
$inventoryPath = "D:\homelab\ansible\inventory\hosts.ini"

# VM names to remove
$vmNames = @(
    "k8s-master-01",
    "k8s-worker-01",
    "k8s-worker-02"
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

function Get-RunningVMs {
    <#
    .SYNOPSIS
    Get list of currently running VMs from vmrun
    #>
    
    $result = & $vmrunPath list 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Warning: Could not query running VMs" "WARNING"
        return @()
    }
    
    # Parse vmrun list output (first line is count, rest are paths)
    $lines = $result -split "`n" | Select-Object -Skip 1
    return $lines | Where-Object { $_ -match '\.vmx$' }
}

function Stop-ClusterVM {
    param(
        [string]$VMXPath,
        [string]$VMName
    )
    
    Write-Log "Stopping VM: $VMName" "INFO"
    
    # Check if VM is running
    $runningVMs = Get-RunningVMs
    $isRunning = $runningVMs | Where-Object { $_ -like "*$VMName*" }
    
    if (-not $isRunning) {
        Write-Log "  VM is not running (already stopped)" "INFO"
        return
    }
    
    if ($PSCmdlet.ShouldProcess($VMName, "Stop VM")) {
        # Try graceful shutdown first
        Write-Log "  Attempting graceful shutdown..." "INFO"
        $stopResult = & $vmrunPath stop $VMXPath soft 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "  [OK] VM stopped gracefully" "SUCCESS"
        } else {
            # Graceful failed, force shutdown
            Write-Log "  Graceful shutdown failed, forcing..." "WARNING"
            $killResult = & $vmrunPath stop $VMXPath hard 2>&1
            
            if ($LASTEXITCODE -eq 0) {
                Write-Log "  [OK] VM stopped (forced)" "SUCCESS"
            } else {
                Write-Log "  Failed to stop VM: $killResult" "ERROR"
                throw "Could not stop $VMName"
            }
        }
        
        # Wait for VM to fully stop
        Start-Sleep -Seconds 3
    }
}

function Remove-ClusterVM {
    param(
        [string]$VMName
    )
    
    $vmDir = Join-Path $clusterDir $VMName
    $vmxPath = Join-Path $vmDir "$VMName.vmx"
    
    Write-Log "Removing VM: $VMName" "INFO"
    
    # Check if VM directory exists
    if (-not (Test-Path $vmDir)) {
        Write-Log "  VM directory does not exist (already removed)" "INFO"
        return
    }
    
    # Stop VM if running
    if (Test-Path $vmxPath) {
        Stop-ClusterVM -VMXPath $vmxPath -VMName $VMName
    }
    
    # Remove VM directory
    if ($PSCmdlet.ShouldProcess($vmDir, "Remove VM directory")) {
        try {
            Remove-Item -Path $vmDir -Recurse -Force -ErrorAction Stop
            Write-Log "  [OK] VM directory removed: $vmDir" "SUCCESS"
        } catch {
            Write-Log "  Error removing directory: $_" "ERROR"
            throw
        }
    }
}

function Remove-AnsibleInventory {
    Write-Log "Removing Ansible inventory: $inventoryPath" "INFO"
    
    if (-not (Test-Path $inventoryPath)) {
        Write-Log "  Inventory file does not exist (already removed)" "INFO"
        return
    }
    
    if ($PSCmdlet.ShouldProcess($inventoryPath, "Remove inventory file")) {
        Remove-Item -Path $inventoryPath -Force
        Write-Log "  [OK] Inventory file removed" "SUCCESS"
    }
}

function Show-ConfirmationPrompt {
    param([string]$Message)
    
    Write-Host "`n$Message" -ForegroundColor Yellow
    $response = Read-Host "Continue? (yes/no)"
    
    return $response -eq "yes"
}

# ================================================================================
# MAIN EXECUTION
# ================================================================================

try {
    Write-Log "========================================" "INFO"
    Write-Log "Stage 2.2: VM Deprovisioning" "INFO"
    Write-Log "========================================" "INFO"
    
    # Show what will be removed
    Write-Log "`nVMs to be removed:" "INFO"
    foreach ($vm in $vmNames) {
        $vmDir = Join-Path $clusterDir $vm
        $exists = Test-Path $vmDir
        $status = if ($exists) { "[EXISTS]" } else { "[NOT FOUND]" }
        Write-Log "  - $vm $status" "INFO"
    }
    
    if (-not $KeepInventory -and (Test-Path $inventoryPath)) {
        Write-Log "`nAnsible inventory will be removed:" "WARNING"
        Write-Log "  - $inventoryPath" "WARNING"
    }
    
    # Confirmation prompt (unless -Force is used)
    if (-not $Force) {
        Write-Host ""
        if (-not (Show-ConfirmationPrompt "This will DESTROY all cluster VMs and cannot be undone.")) {
            Write-Log "Deprovisioning cancelled by user" "WARNING"
            exit 0
        }
    }
    
    # Step 1: Stop and remove VMs
    Write-Log "`nPhase 1: Stopping and removing VMs" "INFO"
    
    foreach ($vmName in $vmNames) {
        Remove-ClusterVM -VMName $vmName
    }
    
    # Step 2: Remove inventory file (unless -KeepInventory is set)
    if (-not $KeepInventory) {
        Write-Log "`nPhase 2: Removing Ansible inventory" "INFO"
        Remove-AnsibleInventory
    } else {
        Write-Log "`nPhase 2: Preserving Ansible inventory (as requested)" "INFO"
    }
    
    # Step 3: Cleanup check
    Write-Log "`nPhase 3: Verifying cleanup" "INFO"
    
    $remainingVMs = Get-ChildItem $clusterDir -Directory | 
        Where-Object { $vmNames -contains $_.Name }
    
    if ($remainingVMs) {
        Write-Log "WARNING: Some VM directories still exist:" "WARNING"
        $remainingVMs | ForEach-Object { Write-Log "  - $($_.FullName)" "WARNING" }
    } else {
        Write-Log "  [OK] All VM directories removed" "SUCCESS"
    }
    
    # Check for any running VMs that should have been stopped
    $runningVMs = Get-RunningVMs
    $clusterVMsRunning = $runningVMs | Where-Object { 
        $vmPath = $_
        $vmNames | Where-Object { $vmPath -like "*$_*" }
    }
    
    if ($clusterVMsRunning) {
        Write-Log "WARNING: Some VMs are still running:" "WARNING"
        $clusterVMsRunning | ForEach-Object { Write-Log "  - $_" "WARNING" }
    } else {
        Write-Log "  [OK] No cluster VMs running" "SUCCESS"
    }
    
    # Summary
    Write-Log "`n========================================" "SUCCESS"
    Write-Log "Deprovisioning Complete!" "SUCCESS"
    Write-Log "========================================" "SUCCESS"
    
    if ($KeepInventory) {
        Write-Log "`nNote: Inventory file preserved at:" "INFO"
        Write-Log "  $inventoryPath" "INFO"
    }
    
    Write-Log "`nCluster directory cleaned:" "INFO"
    Write-Log "  $clusterDir" "INFO"
    
    Write-Log "`nTo reprovision cluster:" "INFO"
    Write-Log "  .\scripts\provision-vms.ps1" "INFO"
    
} catch {
    Write-Log "ERROR: $_" "ERROR"
    Write-Log $_.ScriptStackTrace "ERROR"
    exit 1
}
