# Grant SeServiceLogonRight ("Log on as a service") to a local user
# via LSA Policy API (advapi32!LsaAddAccountRights). This is the same
# mechanism services.msc / NSSM use internally — it bypasses secedit's
# whole-policy reconciliation which can fail on stale entries.
#
# Default target: amashio. Pass -User to override.
# Must be invoked from an elevated session.

param(
    [string]$User = 'amashio',
    [string]$Privilege = 'SeServiceLogonRight'
)

$ErrorActionPreference = 'Stop'

# Admin check
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator
)
if (-not $isAdmin) {
    Write-Host '[ERROR] Must run as Administrator.' -ForegroundColor Red
    exit 1
}

# Resolve SID
try {
    $sid = (New-Object System.Security.Principal.NTAccount($User)).Translate([System.Security.Principal.SecurityIdentifier])
    Write-Host "Target: $User"
    Write-Host "SID   : $($sid.Value)"
    Write-Host "Right : $Privilege"
} catch {
    Write-Host "[ERROR] Could not resolve account '$User': $_" -ForegroundColor Red
    exit 1
}

# Build SID byte array
$sidBytes = New-Object byte[] $sid.BinaryLength
$sid.GetBinaryForm($sidBytes, 0)

# Add-Type with P/Invoke definitions
$src = @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class LsaUtility {
    [StructLayout(LayoutKind.Sequential)]
    public struct LSA_UNICODE_STRING {
        public ushort Length;
        public ushort MaximumLength;
        public IntPtr Buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct LSA_OBJECT_ATTRIBUTES {
        public int Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public uint Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }

    const uint POLICY_CREATE_ACCOUNT = 0x00000010;
    const uint POLICY_LOOKUP_NAMES = 0x00000800;

    [DllImport("advapi32.dll")]
    static extern uint LsaOpenPolicy(
        IntPtr SystemName,
        ref LSA_OBJECT_ATTRIBUTES ObjectAttributes,
        uint DesiredAccess,
        out IntPtr PolicyHandle);

    [DllImport("advapi32.dll")]
    static extern uint LsaAddAccountRights(
        IntPtr PolicyHandle,
        byte[] AccountSid,
        LSA_UNICODE_STRING[] UserRights,
        uint CountOfRights);

    [DllImport("advapi32.dll")]
    static extern uint LsaClose(IntPtr ObjectHandle);

    [DllImport("advapi32.dll")]
    static extern int LsaNtStatusToWinError(uint Status);

    public static int Grant(byte[] sidBytes, string privilege) {
        LSA_OBJECT_ATTRIBUTES oa = new LSA_OBJECT_ATTRIBUTES();
        oa.Length = Marshal.SizeOf(typeof(LSA_OBJECT_ATTRIBUTES));

        IntPtr policyHandle;
        uint status = LsaOpenPolicy(IntPtr.Zero, ref oa,
            POLICY_CREATE_ACCOUNT | POLICY_LOOKUP_NAMES, out policyHandle);
        if (status != 0) {
            return LsaNtStatusToWinError(status);
        }

        try {
            IntPtr buf = Marshal.StringToHGlobalUni(privilege);
            try {
                LSA_UNICODE_STRING[] rights = new LSA_UNICODE_STRING[1];
                rights[0].Length = (ushort)(privilege.Length * 2);
                rights[0].MaximumLength = (ushort)((privilege.Length + 1) * 2);
                rights[0].Buffer = buf;

                uint addStatus = LsaAddAccountRights(policyHandle, sidBytes, rights, 1);
                return LsaNtStatusToWinError(addStatus);
            } finally {
                Marshal.FreeHGlobal(buf);
            }
        } finally {
            LsaClose(policyHandle);
        }
    }
}
"@

Add-Type -TypeDefinition $src -Language CSharp

$rc = [LsaUtility]::Grant($sidBytes, $Privilege)

if ($rc -eq 0) {
    Write-Host ''
    Write-Host "[OK] Granted $Privilege to $User via LsaAddAccountRights." -ForegroundColor Green
    Write-Host 'You can now set the service Log On account via services.msc:'
    Write-Host '  services.msc -> Pic2PDF Viewer -> Properties -> Log On tab'
    Write-Host '  -> This account: .\amashio + Windows password'
    exit 0
} else {
    $msg = (New-Object System.ComponentModel.Win32Exception($rc)).Message
    Write-Host ''
    Write-Host "[ERROR] LsaAddAccountRights failed: Win32 error $rc ($msg)" -ForegroundColor Red
    exit 1
}
