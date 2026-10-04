# Monitoring in Cloud Monitoring, always on and with no server to run (same
# pattern as uplift-modeling-pipeline's infra/alerts.tf). Cloud Run's built-in
# request metrics are free; log-based metrics turn the service's log lines into
# series: the per-turn `llm_turn` JSON (src/assistant/observability/trace.py)
# and the jobs' `job_done ... failed=N`. Alerts mail var.alert_email for
# production. Grafana runs locally (monitoring/) with a read-only account.

variable "alert_email" {
  description = "Address that receives the production alerts."
  type        = string
}

resource "google_project_service" "monitoring" {
  for_each           = toset(["monitoring.googleapis.com", "logging.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

locals {
  # Both environments; the alerts below narrow to production.
  log_base = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=~\"^assistant(-staging)?$\""
  llm_turn = "${local.log_base} AND textPayload:\"llm_turn\""
  prod     = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"assistant\""
  # REGEXP_EXTRACT of one numeric field of the llm_turn JSON. The same patterns
  # are asserted in tests/test_trace.py.
  extract = { for f in ["cost_usd", "latency_ms", "tokens_out"] :
    f => "REGEXP_EXTRACT(textPayload, \"\\\"${f}\\\": ([-0-9.eE+]+)\")"
  }
  # Label on the LLM series, so cost and latency compare across prompt versions.
  prompt_version = "REGEXP_EXTRACT(textPayload, \"\\\"prompt_version\\\": \\\"([0-9a-f]+)\\\"\")"
}

resource "google_logging_metric" "llm_turns" {
  name             = "llm_turns"
  description      = "LLM turns (one llm_turn log line each)."
  filter           = local.llm_turn
  label_extractors = { prompt_version = local.prompt_version }
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key         = "prompt_version"
      description = "sha256 prefix of the system prompt and tools"
    }
  }
  depends_on = [google_project_service.monitoring]
}

resource "google_logging_metric" "llm_rejected" {
  name        = "llm_rejected"
  description = "LLM turns with at least one rejected tool call."
  filter      = "${local.llm_turn} AND textPayload=~\"\\\"rejected\\\": [1-9]\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
  depends_on = [google_project_service.monitoring]
}

resource "google_logging_metric" "job_failed" {
  name        = "job_failed"
  description = "Scheduled job runs where at least one chat failed."
  filter      = "${local.log_base} AND textPayload=~\"job_done .*failed=[1-9]\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
  depends_on = [google_project_service.monitoring]
}

resource "google_logging_metric" "llm_distribution" {
  for_each = {
    # name           = [unit, exponential scale, buckets]: covers the real range
    llm_cost_usd   = ["USD", 0.000001, 30] # 1e-6 .. ~500 USD per turn
    llm_latency_ms = ["ms", 50, 12]        # 50 ms .. ~100 s
    llm_tokens_out = ["1", 8, 12]          # 8 .. ~16k tokens
  }
  name             = each.key
  description      = "Per-turn ${trimprefix(each.key, "llm_")} from the llm_turn log line."
  filter           = local.llm_turn
  value_extractor  = local.extract[trimprefix(each.key, "llm_")]
  label_extractors = { prompt_version = local.prompt_version }
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = each.value[0]
    labels {
      key         = "prompt_version"
      description = "sha256 prefix of the system prompt and tools"
    }
  }
  bucket_options {
    exponential_buckets {
      num_finite_buckets = each.value[2]
      growth_factor      = 2
      scale              = each.value[1]
    }
  }
  depends_on = [google_project_service.monitoring]
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "assistant alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
  depends_on = [google_project_service.monitoring]
}

resource "google_monitoring_alert_policy" "service_5xx" {
  display_name          = "assistant 5xx responses"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "more than 5 responses with 5xx in 5 min"
    condition_threshold {
      # Includes the 503 /push returns when DeepSeek is down (Pub/Sub retries).
      filter          = "${local.prod} AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "service_latency" {
  display_name          = "assistant p99 latency above 25 s"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "p99 request latency > 25 s for 10 min"
    condition_threshold {
      # Not uplift's 1 s: the /push requests run LLM turns that take seconds by
      # design. 25 s means turns are hanging toward the 30 s DeepSeek timeout.
      filter          = "${local.prod} AND metric.type = \"run.googleapis.com/request_latencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = 25000
      duration        = "600s"
      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
        cross_series_reducer = "REDUCE_MAX"
      }
    }
  }
  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "jobs_failed" {
  display_name          = "assistant scheduled jobs failing"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "a job run failed for some chat in the last hour"
    condition_threshold {
      filter          = "${local.prod} AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.job_failed.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
  alert_strategy {
    auto_close = "7200s"
  }
}

resource "google_monitoring_alert_policy" "llm_rejected" {
  display_name          = "assistant LLM tool calls rejected"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "more than 3 turns with rejected tool calls in 1 h"
    condition_threshold {
      # A spike means the prompt or a tool schema drifted from the model.
      filter          = "${local.prod} AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.llm_rejected.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 3
      duration        = "0s"
      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
  alert_strategy {
    auto_close = "7200s"
  }
}

# Read-only account for the local Grafana (monitoring/). Its key is created on
# demand by monitoring/grafana-key.sh, kept only on the owner's machine
# (git-ignored), and grants nothing but reading metrics.
resource "google_service_account" "grafana" {
  account_id   = "assistant-grafana"
  display_name = "Local Grafana: reads Cloud Monitoring"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "grafana_reads_metrics" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = google_service_account.grafana.member
}
