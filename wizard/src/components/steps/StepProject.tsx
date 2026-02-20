import {
  TextInput,
  NumberInput,
  Select,
  Switch,
  Stack,
  Title,
  Text,
} from "@mantine/core";
import type { WizardState } from "@/types/wizard";

interface Props {
  state: WizardState;
  onChange: (patch: Partial<WizardState>) => void;
}

export function StepProject({ state, onChange }: Props) {
  return (
    <Stack gap="lg">
      <div>
        <Title order={3}>專案基本設定</Title>
        <Text size="sm" c="dimmed">
          設定你的 AutoCRUD 專案名稱與基本參數
        </Text>
      </div>

      <TextInput
        label="專案名稱"
        description="用於 pyproject.toml 中的 package name"
        placeholder="my-autocrud-app"
        value={state.projectName}
        onChange={(e) => onChange({ projectName: e.currentTarget.value })}
      />

      <TextInput
        label="FastAPI Title"
        description="顯示在 Swagger UI 的 API 標題"
        placeholder="My AutoCRUD API"
        value={state.fastapiTitle}
        onChange={(e) => onChange({ fastapiTitle: e.currentTarget.value })}
      />

      <Select
        label="Python 版本"
        description="pyproject.toml requires-python 版本"
        data={[
          { value: "3.11", label: "Python 3.11" },
          { value: "3.12", label: "Python 3.12" },
          { value: "3.13", label: "Python 3.13" },
        ]}
        value={state.pythonVersion}
        onChange={(v) =>
          onChange({
            pythonVersion: (v as WizardState["pythonVersion"]) || "3.12",
          })
        }
      />

      <NumberInput
        label="Server Port"
        description="uvicorn 啟動的 port"
        min={1}
        max={65535}
        value={state.port}
        onChange={(v) => onChange({ port: typeof v === "number" ? v : 8000 })}
      />

      <Switch
        label="啟用 CORS"
        description="開啟 CORSMiddleware（allow_origins=['*']），搭配前端使用時必須開啟"
        checked={state.enableCORS}
        onChange={(e) => onChange({ enableCORS: e.currentTarget.checked })}
      />
    </Stack>
  );
}
