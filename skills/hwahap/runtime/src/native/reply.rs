use super::NativeCompletion;
use crate::{Error, Result};

/// A reused thread's previous answer must never stand in for its new dispatch.
pub(super) fn result(completion: &NativeCompletion, required: bool) -> Result<String> {
    let value = serde_json::from_str::<serde_json::Value>(&completion.final_message).ok();
    if let Some(value) = value.filter(|value| value.get("dispatch_id").is_some()) {
        if value["dispatch_id"].as_str() != Some(&completion.dispatch_id)
            || !value["result"].is_object()
        {
            return Err(Error::Rejected(
                "native reply does not identify this exact dispatch and result".into(),
            ));
        }
        return serde_json::to_string(&value["result"]).map_err(|e| Error::Internal(e.to_string()));
    }
    if required {
        Err(Error::Rejected(
            "a reused agent must return the dispatch_id/result envelope".into(),
        ))
    } else {
        Ok(completion.final_message.clone())
    }
}
