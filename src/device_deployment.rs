//! Optional registration approval using the companion OSS API.
use serde_json::{json, Value};
use std::{env, time::Duration};

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Decision {
    Allowed,
    NotDeployed,
    IdTaken,
    ServiceError,
}

pub(crate) fn enabled() -> bool {
    matches!(
        env::var("REQUIRE_DEVICE_DEPLOYMENT")
            .unwrap_or_default()
            .to_ascii_uppercase()
            .as_str(),
        "Y" | "YES" | "TRUE" | "1"
    )
}

pub(crate) fn configured() -> bool {
    !env::var("RUSTDESK_API_INTERNAL_KEY").unwrap_or_default().is_empty()
}

fn parse_result(body: &str) -> Decision {
    match serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|value| value.get("result")?.as_str().map(str::to_owned))
        .as_deref()
    {
        Some("OK") => Decision::Allowed,
        Some("NOT_DEPLOYED") => Decision::NotDeployed,
        Some("ID_TAKEN") => Decision::IdTaken,
        _ => Decision::ServiceError,
    }
}

pub(crate) async fn authorize(id: &str, uuid: &[u8], pk: &[u8]) -> Decision {
    if !enabled() {
        return Decision::Allowed;
    }
    let key = match env::var("RUSTDESK_API_INTERNAL_KEY") {
        Ok(value) if !value.is_empty() => value,
        _ => return Decision::ServiceError,
    };
    let url = env::var("RUSTDESK_API_INTERNAL_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:21114/internal/v1/device/authorize".to_owned());
    let id = id.to_owned();
    let uuid = base64::encode(uuid);
    let pk = base64::encode(pk);
    match hbb_common::tokio::task::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(3))
            .build()
            .map_err(|err| err.to_string())?;
        let response = client
            .post(url)
            .header("X-RustDesk-Internal-Key", key)
            .json(&json!({"id": id, "uuid": uuid, "pk": pk}))
            .send()
            .map_err(|err| err.to_string())?;
        if !response.status().is_success() {
            return Err(format!("HTTP {}", response.status()));
        }
        response.text().map_err(|err| err.to_string())
    })
    .await
    {
        Ok(Ok(body)) => parse_result(&body),
        _ => Decision::ServiceError,
    }
}

#[cfg(test)]
mod tests {
    use super::{parse_result, Decision};

    #[test]
    fn checks_companion_api_response() {
        assert_eq!(parse_result(r#"{"result":"OK"}"#), Decision::Allowed);
        assert_eq!(parse_result(r#"{"result":"NOT_DEPLOYED"}"#), Decision::NotDeployed);
        assert_eq!(parse_result(r#"{"result":"NOT_ENABLED"}"#), Decision::ServiceError);
        assert_eq!(parse_result(r#"{"result":"ID_TAKEN"}"#), Decision::IdTaken);
        assert_eq!(parse_result("garbage"), Decision::ServiceError);
        assert_eq!(parse_result(r#"{"result":"DENIED"}"#), Decision::ServiceError);
    }
}
