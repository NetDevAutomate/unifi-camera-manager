"""Test harness for AXIS camera authentication across different APIs.

This script systematically tests credential combinations against each AXIS API endpoint
to determine the correct authentication requirements for each API.

Usage:
    uv run python tests/test_axis_auth.py --ip 192.168.10.12
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@dataclass
class AuthTestResult:
    """Result of an authentication test against an API endpoint."""

    api_name: str
    endpoint: str
    auth_type: str  # "digest" or "basic"
    credential_source: str  # "onvif", "axis", "env_axis", "env_onvif"
    username: str
    status_code: int
    success: bool
    error_message: str = ""
    response_preview: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class APIEndpoint:
    """Definition of an AXIS API endpoint to test."""

    name: str
    path: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    description: str = ""


# AXIS API endpoints to test
AXIS_ENDPOINTS = [
    APIEndpoint(
        name="param_v2beta_root",
        path="/config/rest/param/v2beta",
        headers={"accept": "application/json"},
        description="VAPIX param v2beta API - full config",
    ),
    APIEndpoint(
        name="param_v2beta_brand",
        path="/config/rest/param/v2beta/Brand",
        headers={"accept": "application/json"},
        description="VAPIX param v2beta API - Brand info",
    ),
    APIEndpoint(
        name="param_v2beta_network",
        path="/config/rest/param/v2beta/Network",
        headers={"accept": "application/json"},
        description="VAPIX param v2beta API - Network config",
    ),
    APIEndpoint(
        name="param_v2beta_rtsp",
        path="/config/rest/param/v2beta/Network/RTSP",
        headers={"accept": "application/json"},
        description="VAPIX param v2beta API - RTSP config",
    ),
    APIEndpoint(
        name="param_v2beta_rtp",
        path="/config/rest/param/v2beta/Network/RTP",
        headers={"accept": "application/json"},
        description="VAPIX param v2beta API - RTP config",
    ),
    APIEndpoint(
        name="param_v2beta_stream_profile",
        path="/config/rest/param/v2beta/StreamProfile",
        headers={"accept": "application/json"},
        description="VAPIX param v2beta API - Stream profiles",
    ),
    APIEndpoint(
        name="lldp_v1_status",
        path="/config/rest/lldp/v1",
        headers={"accept": "application/json"},
        description="LLDP REST API - status",
    ),
    APIEndpoint(
        name="lldp_v1_neighbors",
        path="/config/rest/lldp/v1/neighbors",
        headers={"accept": "application/json"},
        description="LLDP REST API - neighbors",
    ),
    APIEndpoint(
        name="serverreport_text",
        path="/axis-cgi/serverreport.cgi",
        description="VAPIX serverreport.cgi - logs (text mode)",
    ),
    APIEndpoint(
        name="serverreport_tar",
        path="/axis-cgi/serverreport.cgi?mode=tar_all",
        description="VAPIX serverreport.cgi - logs (tar mode)",
    ),
    APIEndpoint(
        name="param_cgi_list",
        path="/axis-cgi/param.cgi?action=list",
        description="VAPIX param.cgi - legacy parameter API",
    ),
    APIEndpoint(
        name="basicdeviceinfo",
        path="/axis-cgi/basicdeviceinfo.cgi",
        headers={"accept": "application/json"},
        description="VAPIX basicdeviceinfo.cgi - device info",
    ),
]


@dataclass
class CredentialSet:
    """A set of credentials to test."""

    name: str
    username: str
    password: str
    source: str  # Description of where credentials came from


def get_credential_sets() -> list[CredentialSet]:
    """Get all available credential sets to test."""
    creds = []

    # From environment - AXIS admin credentials
    axis_user = os.getenv("AXIS_ADMIN_USERNAME")
    axis_pass = os.getenv("AXIS_ADMIN_PASSWORD")
    if axis_user and axis_pass:
        creds.append(
            CredentialSet(
                name="env_axis_admin",
                username=axis_user,
                password=axis_pass,
                source="AXIS_ADMIN_USERNAME/PASSWORD env vars",
            )
        )

    # From environment - ONVIF credentials
    onvif_user = os.getenv("ONVIF_USER")
    onvif_pass = os.getenv("ONVIF_PASSWORD")
    if onvif_user and onvif_pass:
        creds.append(
            CredentialSet(
                name="env_onvif",
                username=onvif_user,
                password=onvif_pass,
                source="ONVIF_USER/PASSWORD env vars",
            )
        )

    # Common defaults to try
    common_defaults = [
        ("root", "pass", "AXIS default root"),
        ("admin", "admin", "Common admin default"),
        ("root", "root", "Simple root default"),
    ]

    for user, passwd, desc in common_defaults:
        # Don't add if already covered by env vars
        if not any(c.username == user and c.password == passwd for c in creds):
            creds.append(
                CredentialSet(name=f"default_{user}", username=user, password=passwd, source=desc)
            )

    return creds


async def try_endpoint_auth(
    client: httpx.AsyncClient,
    base_url: str,
    endpoint: APIEndpoint,
    cred: CredentialSet,
    auth_type: str,
) -> AuthTestResult:
    """Try authenticating to an endpoint with specific credentials and auth type."""
    url = f"{base_url}{endpoint.path}"

    try:
        if auth_type == "digest":
            auth = httpx.DigestAuth(cred.username, cred.password)
        else:
            auth = httpx.BasicAuth(cred.username, cred.password)

        response = await client.get(url, auth=auth, headers=endpoint.headers, timeout=10.0)

        # Get response preview (first 200 chars)
        try:
            if response.headers.get("content-type", "").startswith("application/json"):
                preview = response.text[:500]
            else:
                preview = response.text[:200]
        except Exception:
            preview = f"<binary data, {len(response.content)} bytes>"

        return AuthTestResult(
            api_name=endpoint.name,
            endpoint=endpoint.path,
            auth_type=auth_type,
            credential_source=cred.name,
            username=cred.username,
            status_code=response.status_code,
            success=response.status_code == 200,
            response_preview=preview if response.status_code == 200 else "",
            error_message="" if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    except httpx.TimeoutException:
        return AuthTestResult(
            api_name=endpoint.name,
            endpoint=endpoint.path,
            auth_type=auth_type,
            credential_source=cred.name,
            username=cred.username,
            status_code=0,
            success=False,
            error_message="Timeout",
        )
    except Exception as e:
        return AuthTestResult(
            api_name=endpoint.name,
            endpoint=endpoint.path,
            auth_type=auth_type,
            credential_source=cred.name,
            username=cred.username,
            status_code=0,
            success=False,
            error_message=str(e),
        )


async def run_auth_tests(ip_address: str, port: int = 80) -> list[AuthTestResult]:
    """Run all authentication tests against all endpoints."""
    base_url = f"http://{ip_address}:{port}"
    results: list[AuthTestResult] = []
    creds = get_credential_sets()

    print(f"\n{'=' * 70}")
    print("AXIS Authentication Test Harness")
    print(f"Target: {base_url}")
    print(f"Credential sets to test: {len(creds)}")
    print(f"Endpoints to test: {len(AXIS_ENDPOINTS)}")
    print("Auth types: digest, basic")
    print(f"Total tests: {len(creds) * len(AXIS_ENDPOINTS) * 2}")
    print(f"{'=' * 70}\n")

    async with httpx.AsyncClient(verify=False) as client:
        for endpoint in AXIS_ENDPOINTS:
            print(f"\nTesting: {endpoint.name} ({endpoint.path})")
            print(f"  {endpoint.description}")

            for cred in creds:
                for auth_type in ["digest", "basic"]:
                    result = await try_endpoint_auth(client, base_url, endpoint, cred, auth_type)
                    results.append(result)

                    status = "✓" if result.success else "✗"
                    print(
                        f"  [{status}] {auth_type:6} {cred.name:20} "
                        f"-> {result.status_code} {result.error_message}"
                    )

    return results


def analyze_results(results: list[AuthTestResult]) -> dict[str, Any]:
    """Analyze test results to determine optimal credential/auth combinations."""
    analysis: dict[str, Any] = {
        "summary": {
            "total_tests": len(results),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
        },
        "by_endpoint": {},
        "by_credential": {},
        "recommendations": {},
    }

    # Group by endpoint
    endpoints: dict[str, list[AuthTestResult]] = {}
    for r in results:
        if r.api_name not in endpoints:
            endpoints[r.api_name] = []
        endpoints[r.api_name].append(r)

    for api_name, api_results in endpoints.items():
        successful = [r for r in api_results if r.success]
        analysis["by_endpoint"][api_name] = {
            "total_tests": len(api_results),
            "successful": len(successful),
            "working_combinations": [
                {
                    "credential": r.credential_source,
                    "auth_type": r.auth_type,
                    "username": r.username,
                }
                for r in successful
            ],
        }

        # Determine recommendation for this endpoint
        if successful:
            # Prefer digest auth over basic
            digest_success = [r for r in successful if r.auth_type == "digest"]
            rec = digest_success[0] if digest_success else successful[0]

            analysis["recommendations"][api_name] = {
                "credential_source": rec.credential_source,
                "auth_type": rec.auth_type,
                "username": rec.username,
            }
        else:
            analysis["recommendations"][api_name] = {
                "credential_source": "NONE_WORKING",
                "auth_type": "unknown",
                "username": "unknown",
                "error": "No working credential combination found",
            }

    # Group by credential
    creds_dict: dict[str, list[AuthTestResult]] = {}
    for r in results:
        if r.credential_source not in creds_dict:
            creds_dict[r.credential_source] = []
        creds_dict[r.credential_source].append(r)

    for cred_name, cred_results in creds_dict.items():
        successful = [r for r in cred_results if r.success]
        analysis["by_credential"][cred_name] = {
            "total_tests": len(cred_results),
            "successful": len(successful),
            "success_rate": len(successful) / len(cred_results) * 100 if cred_results else 0,
            "working_endpoints": list({r.api_name for r in successful}),
        }

    return analysis


def print_analysis(analysis: dict[str, Any]) -> None:
    """Print analysis results in a readable format."""
    print(f"\n{'=' * 70}")
    print("ANALYSIS RESULTS")
    print(f"{'=' * 70}")

    print("\nSummary:")
    print(f"  Total tests: {analysis['summary']['total_tests']}")
    print(f"  Successful:  {analysis['summary']['successful']}")
    print(f"  Failed:      {analysis['summary']['failed']}")

    print(f"\n{'-' * 70}")
    print("Recommendations by Endpoint:")
    print(f"{'-' * 70}")

    for api_name, rec in analysis["recommendations"].items():
        if rec.get("error"):
            print(f"\n  {api_name}:")
            print(f"    ERROR: {rec['error']}")
        else:
            print(f"\n  {api_name}:")
            print(f"    Credential: {rec['credential_source']}")
            print(f"    Auth type:  {rec['auth_type']}")
            print(f"    Username:   {rec['username']}")

    print(f"\n{'-' * 70}")
    print("Credential Performance:")
    print(f"{'-' * 70}")

    for cred_name, stats in analysis["by_credential"].items():
        print(f"\n  {cred_name}:")
        print(f"    Success rate: {stats['success_rate']:.1f}%")
        print(f"    Working endpoints: {', '.join(stats['working_endpoints']) or 'None'}")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test AXIS camera authentication")
    parser.add_argument("--ip", required=True, help="Camera IP address")
    parser.add_argument("--port", type=int, default=80, help="HTTP port (default: 80)")
    parser.add_argument("--output", "-o", help="Output JSON file for results")
    args = parser.parse_args()

    results = await run_auth_tests(args.ip, args.port)
    analysis = analyze_results(results)

    print_analysis(analysis)

    # Save results to JSON
    output_file = args.output or f"auth_test_results_{args.ip.replace('.', '_')}.json"
    output_data = {
        "target": {"ip": args.ip, "port": args.port},
        "timestamp": datetime.now().isoformat(),
        "results": [asdict(r) for r in results],
        "analysis": analysis,
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n\nResults saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
