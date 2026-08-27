import React from "react";
import { Tag, Typography, Progress, Empty } from "antd";

const { Text, Paragraph } = Typography;

/**
 * Gate 2 Step 10 - the evidence beside a machine suggestion.
 *
 * The risk this component exists to address is not that suggestions are wrong.
 * It is that they look authoritative and get rubber-stamped without being read.
 * So the reviewer is shown what the machine actually saw - the data type, how
 * many distinct values there were, and the sample values themselves - and can
 * disagree on the evidence rather than on trust.
 *
 * Where samples were withheld this says so explicitly and gives the reason.
 * An empty sample list rendered as a blank box reads as a bug; "withheld
 * because the column holds personal names" reads as a decision.
 *
 * All colours come from CSS custom properties defined for both themes in
 * index.css, or from antd Tag presets, so light and dark both work.
 */

const labelStyle = {
  color: "var(--text-secondary)",
  fontSize: 12,
  textTransform: "uppercase",
  letterSpacing: "0.04em"
};

const valueStyle = {
  color: "var(--text-main)",
  fontSize: 14,
  fontWeight: 500
};

const Stat = ({ label, children }) => (
  <div style={{ minWidth: 120 }}>
    <div style={labelStyle}>{label}</div>
    <div style={valueStyle}>{children}</div>
  </div>
);

const confidenceColour = (confidence) => {
  if (confidence >= 0.85) return "#16a34a";
  if (confidence >= 0.7) return "#d97706";
  return "#dc2626";
};

export default function EvidencePanel({ evidence, confidence, reasoning }) {
  if (!evidence) {
    return (
      <Empty
        description={
          <span style={{ color: "var(--text-secondary)" }}>
            No evidence was recorded for this suggestion.
          </span>
        }
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  const {
    data_type,
    distinct_count,
    null_fraction,
    samples,
    samples_withheld,
    samples_withheld_reason,
    row_count_profiled,
    date_like_columns,
    period_like_columns
  } = evidence;

  const isTableEvidence =
    date_like_columns !== undefined || period_like_columns !== undefined;

  return (
    <div
      style={{
        background: "var(--bg-card-inner)",
        border: "1px solid var(--border-color)",
        borderRadius: 8,
        padding: 16
      }}
    >
      <div style={{ ...labelStyle, marginBottom: 12 }}>
        Evidence the suggestion was based on
      </div>

      {isTableEvidence ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 24,
            marginBottom: 16
          }}
        >
          <Stat label="Date-like columns">
            {(date_like_columns || []).length === 0 ? (
              <Text style={{ color: "var(--text-secondary)" }}>None</Text>
            ) : (
              date_like_columns.map((c) => (
                <Tag key={c} style={{ marginBottom: 4 }}>
                  {c}
                </Tag>
              ))
            )}
          </Stat>

          <Stat label="Period-like columns">
            {(period_like_columns || []).length === 0 ? (
              <Text style={{ color: "var(--text-secondary)" }}>None</Text>
            ) : (
              period_like_columns.map((c) => (
                <Tag key={c} color="blue" style={{ marginBottom: 4 }}>
                  {c}
                </Tag>
              ))
            )}
          </Stat>
        </div>
      ) : (
        <>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 24,
              marginBottom: 16
            }}
          >
            <Stat label="Data type">{data_type || "unknown"}</Stat>

            <Stat label="Distinct values">
              {distinct_count === undefined || distinct_count === null
                ? "unknown"
                : distinct_count.toLocaleString()}
            </Stat>

            <Stat label="Nulls">
              {null_fraction === undefined || null_fraction === null
                ? "unknown"
                : `${(null_fraction * 100).toFixed(1)}%`}
            </Stat>

            <Stat label="Rows profiled">
              {row_count_profiled
                ? row_count_profiled.toLocaleString()
                : "unknown"}
            </Stat>
          </div>

          <div style={{ marginBottom: 16 }}>
            <div style={{ ...labelStyle, marginBottom: 6 }}>Sample values</div>

            {samples_withheld ? (
              // Never render an empty box. State that withholding was a
              // decision, and why - high-cardinality columns hold customer and
              // manager names, which are deliberately not sent for
              // classification.
              <div
                style={{
                  background: "var(--bg-card)",
                  border: "1px dashed var(--border-color)",
                  borderRadius: 6,
                  padding: "10px 12px"
                }}
              >
                <Tag color="default">Samples withheld</Tag>
                <Text
                  style={{
                    color: "var(--text-secondary)",
                    fontSize: 13,
                    display: "block",
                    marginTop: 6
                  }}
                >
                  {samples_withheld_reason ||
                    "Sample values were not collected for this column."}
                </Text>
              </div>
            ) : (samples || []).length === 0 ? (
              <Text style={{ color: "var(--text-secondary)" }}>
                No sample values were returned.
              </Text>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {samples.map((s, i) => (
                  <Tag
                    key={`${s}-${i}`}
                    style={{
                      fontFamily:
                        "ui-monospace, SFMono-Regular, Menlo, monospace",
                      margin: 0
                    }}
                  >
                    {String(s)}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {confidence !== undefined && confidence !== null && (
        <div style={{ marginBottom: 12, maxWidth: 320 }}>
          <div style={{ ...labelStyle, marginBottom: 4 }}>
            Confidence — {(confidence * 100).toFixed(0)}%
          </div>
          <Progress
            percent={Math.round(confidence * 100)}
            showInfo={false}
            strokeColor={confidenceColour(confidence)}
            size="small"
          />
        </div>
      )}

      {reasoning && (
        <div>
          <div style={{ ...labelStyle, marginBottom: 4 }}>Reasoning</div>
          <Paragraph
            style={{
              color: "var(--text-secondary)",
              marginBottom: 0,
              fontSize: 13
            }}
          >
            {reasoning}
          </Paragraph>
        </div>
      )}
    </div>
  );
}
