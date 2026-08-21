import React, { useState } from "react";
import { Card, Button, Typography, Radio } from "antd";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";

const { Text, Title } = Typography;

export default function ClarificationCard({
  title,
  message,
  options = [],
  onConfirm,
  onCancel,
  submitting = false,
  disabled = false
}) {
  const [selectedId, setSelectedId] = useState(null);

  // 1. Calculate occurrence count for each normalized value
  const valueCounts = {};
  options.forEach((opt) => {
    const norm = (opt.value || "").trim().toLowerCase();
    if (norm) {
      valueCounts[norm] = (valueCounts[norm] || 0) + 1;
    }
  });

  const hasDuplicateValues = Object.values(valueCounts).some((count) => count > 1);

  // Dynamic clean message when duplicates exist
  const firstDuplicateVal = options.find((opt) => {
    const norm = (opt.value || "").trim().toLowerCase();
    return valueCounts[norm] > 1;
  })?.value;

  const displayMessage = hasDuplicateValues && firstDuplicateVal
    ? `I found "${firstDuplicateVal}" in multiple business dimensions.\nWhich one did you mean?`
    : message || "Please choose one of the options below to proceed:";

  const handleConfirm = () => {
    const chosen = options.find((opt) => opt.option_id === selectedId);
    if (chosen && onConfirm) {
      const norm = (chosen.value || "").trim().toLowerCase();
      const isDup = valueCounts[norm] > 1;
      const dim = chosen.display_dimension || chosen.dimension || chosen.business_name;
      const displayLabel = isDup && dim ? `${chosen.value} — ${dim}` : chosen.value;
      
      // Pass option_id as the primary selection identifier, and displayLabel for UI representation
      onConfirm(chosen.option_id, displayLabel);
    }
  };

  return (
    <Card
      bordered
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderLeft: "4px solid #6366f1",
        borderRadius: "12px",
        boxShadow: "0 4px 16px rgba(0, 0, 0, 0.08)",
        margin: "12px 0",
        maxWidth: "600px",
        width: "100%"
      }}
      bodyStyle={{ padding: "16px" }}
      data-testid="clarification-card"
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
        <Title level={5} style={{ margin: 0, color: "var(--text-main)", fontWeight: 700 }}>
          {title || "Clarification Required"}
        </Title>
        {onCancel && (
          <Button
            type="text"
            shape="circle"
            size="small"
            icon={<CloseOutlined style={{ color: "var(--text-muted)" }} />}
            onClick={onCancel}
            disabled={disabled || submitting}
            aria-label="Dismiss clarification"
          />
        )}
      </div>

      {/* Description Message */}
      <div style={{ marginBottom: "16px", color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.5", whiteSpace: "pre-line" }}>
        {displayMessage}
      </div>

      {/* Options Area (Scrollable if many options) */}
      <div
        style={{
          maxHeight: "240px",
          overflowY: "auto",
          marginBottom: "16px",
          paddingRight: "4px"
        }}
        className="custom-scrollbar"
      >
        <Radio.Group
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          disabled={disabled || submitting}
          style={{ width: "100%", display: "flex", flexDirection: "column", gap: "8px" }}
        >
          {options.map((opt) => {
            const isSelected = selectedId === opt.option_id;
            const normVal = (opt.value || "").trim().toLowerCase();
            const isDuplicate = valueCounts[normVal] > 1;
            const dimName = opt.display_dimension || opt.dimension || opt.business_name;
            const displayLabel = isDuplicate && dimName ? `${opt.value} — ${dimName}` : opt.value;

            return (
              <label
                key={opt.option_id}
                data-testid={`option-label-${opt.option_id}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: "10px 12px",
                  borderRadius: "8px",
                  border: "1px solid " + (isSelected ? "#6366f1" : "var(--border-color)"),
                  background: isSelected ? "var(--bg-selected-chat)" : "var(--bg-card-inner)",
                  cursor: (disabled || submitting) ? "not-allowed" : "pointer",
                  transition: "all 0.2s ease",
                  outline: "none"
                }}
                className="welcome-suggestion-card"
                onKeyDown={(e) => {
                  if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    if (!disabled && !submitting) {
                      setSelectedId(opt.option_id);
                    }
                  }
                }}
                tabIndex={disabled || submitting ? -1 : 0}
                aria-checked={isSelected}
              >
                <Radio
                  value={opt.option_id}
                  style={{
                    marginRight: "10px",
                    color: "var(--text-main)"
                  }}
                />
                <Text style={{ color: "var(--text-main)", fontSize: "13.5px", fontWeight: isSelected ? 600 : 500 }}>
                  {displayLabel}
                </Text>
              </label>
            );
          })}
        </Radio.Group>
      </div>

      {/* Compact Footer */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", borderTop: "1px solid var(--border-color)", paddingTop: "12px" }}>
        {onCancel && (
          <Button size="small" onClick={onCancel} disabled={disabled || submitting}>
            Cancel
          </Button>
        )}
        <Button
          type="primary"
          size="small"
          icon={<CheckOutlined />}
          onClick={handleConfirm}
          disabled={selectedId === null || disabled}
          loading={submitting}
          style={{
            backgroundColor: selectedId === null ? undefined : "#4f46e5",
            borderColor: selectedId === null ? undefined : "#4f46e5",
            fontWeight: 600
          }}
          data-testid="use-selected-btn"
        >
          Use Selected
        </Button>
      </div>
    </Card>
  );
}
