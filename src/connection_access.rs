//! Optional server-side authorization of RustDesk connection requests.
//! When configured, hbbs asks the OSS API to validate the account session
//! and its permitted target device. The access decision is never cached.
use hbb_common::{log, tokio};
use serde_derive::Deserialize;
use std::{env, time::Duration};

#[derive(Deserialize)]
struct AccessResponse {
    allow: bool,
    #[serde(default)]
    reason: String,
}

fn parse_response(json: &str) -> Result<bool, String> {
    let reply: AccessResponse = serde_json::from_str(json).map_err(|err| err.to_string())?;
    if !reply.allow {
        log::debug!("Connection access denied: {}", reply.reason);
    }
    Ok(reply.allow)
}

pub(crate) fn enabled() -> bool {
    env::var("RUSTDESK_API_CONNECTION_ACCESS_URL")
        .map(|url| !url.trim().is_empty())
        .unwrap_or(false)
}

pub(crate) async fn permitted(device_id: &str, raw_token: &str) -> bool {
    if !enabled() {
        return true;
    }
    if device_id.is_empty() || device_id.len() > 253 ||
        raw_token.is_empty() || raw_token.len() > 4096 {
        return false;
    }
    let url = match env::var("RUSTDESK_API_CONNECTION_ACCESS_URL") {
        Ok(url) if url.starts_with("http://") || url.starts_with("https://") => url,
        _ => return false,
    };
    let key = match env::var("RUSTDESK_API_INTERNAL_KEY") {
        Ok(value) if !value.is_empty() => value,
        _ => {
            log::warn!("RUSTDESK_API_INTERNAL_KEY is required for connection access checks");
            return false;
        }
    };
    let device_id = device_id.to_owned();
    let token = raw_token.to_owned();
    let result = tokio::task::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(4))
            .build()
            .map_err(|err| err.to_string())?;
        let res = client.post(url)
            .header("X-RustDesk-Internal-Key", key)
            .json(&serde_json::json!({"device_id":device_id,"token":token}))
            .send()
            .map_err(|err| err.to_string())?;
        if !res.status().is_success() {
            return Err(format!("connection access API returned HTTP {}",res.status()));
        }
        let body = res.text().map_err(|err| err.to_string())?;
        parse_response(&body)
    }).await;
    match result {
        Ok(Ok(allow)) => allow,
        Ok(Err(err)) => {
            log::warn!("Connection authorization unavailable: {}",err);
            false
        }
        Err(err) => {
            log::warn!("Connection authorization task failed: {}",err);
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn authorization_parser_requires_explicit_allow() {
        assert_eq!(parse_response(r#"{"allow":true,"reason":"rule"}"#).unwrap(),true);
        assert_eq!(parse_response(r#"{"allow":false,"reason":"denied"}"#).unwrap(),false);
        assert!(parse_response(r#"{"reason":"missing allow"}"#).is_err());
        assert!(parse_response(r#"{"allow":"yes"}"#).is_err());
        assert!(parse_response("garbage").is_err());
    }

    #[tokio::test]
    async fn disabled_access_rules_keep_existing_connections() {
        if !enabled() {
            assert!(permitted("any-device","").await);
        }
    }
}
