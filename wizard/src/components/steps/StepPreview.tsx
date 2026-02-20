import { useState, useMemo, useCallback } from 'react';
import {
  Stack,
  Title,
  Text,
  Group,
  Paper,
  NavLink,
  Button,
  CopyButton,
  ActionIcon,
  Tooltip,
  ScrollArea,
  Alert,
} from '@mantine/core';
import {
  IconDownload,
  IconCopy,
  IconCheck,
  IconFile,
  IconAlertCircle,
} from '@tabler/icons-react';
import Editor from '@monaco-editor/react';
import JSZip from 'jszip';
import { saveAs } from 'file-saver';
import { generateProject } from '@/lib/generator';
import type { GeneratedFile } from '@/lib/generator';
import type { WizardState } from '@/types/wizard';

interface Props {
  state: WizardState;
}

export function StepPreview({ state }: Props) {
  const files = useMemo(() => generateProject(state), [state]);
  const [activeFile, setActiveFile] = useState(0);
  const [downloading, setDownloading] = useState(false);

  const currentFile = files[activeFile] || files[0];

  const handleDownload = useCallback(async () => {
    setDownloading(true);
    try {
      const zip = new JSZip();
      for (const f of files) {
        zip.file(f.filename, f.content);
      }
      const blob = await zip.generateAsync({ type: 'blob' });
      saveAs(blob, `${state.projectName || 'autocrud-project'}.zip`);
    } finally {
      setDownloading(false);
    }
  }, [files, state.projectName]);

  // Validation warnings
  const warnings = useMemo(() => {
    const w: string[] = [];
    if (!state.projectName.trim()) w.push('專案名稱未填寫');
    if (state.models.length === 0) w.push('至少需要一個 Model');
    state.models.forEach((m, i) => {
      if (!m.name.trim()) w.push(`Model ${i + 1} 名稱未填寫`);
      if (m.inputMode === 'form' && m.fields.length === 0) {
        w.push(`${m.name || `Model ${i + 1}`} 至少需要一個欄位`);
      }
      if (m.inputMode === 'code' && !m.rawCode.trim()) {
        w.push(`${m.name || `Model ${i + 1}`} code 未填寫`);
      }
    });
    return w;
  }, [state]);

  return (
    <Stack gap="lg">
      <div>
        <Title order={3}>預覽 &amp; 下載</Title>
        <Text size="sm" c="dimmed">
          檢查生成的程式碼，滿意後下載 ZIP
        </Text>
      </div>

      {warnings.length > 0 && (
        <Alert
          icon={<IconAlertCircle size={16} />}
          title="注意事項"
          color="yellow"
        >
          <Stack gap={4}>
            {warnings.map((w, i) => (
              <Text key={i} size="sm">
                • {w}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}

      <Group align="flex-start" gap="md" style={{ minHeight: 450 }}>
        {/* File tree sidebar */}
        <Paper
          withBorder
          w={200}
          style={{ flexShrink: 0, alignSelf: 'stretch' }}
        >
          <ScrollArea h="100%">
            <Stack gap={0} p="xs">
              <Text size="xs" fw={700} c="dimmed" mb="xs" tt="uppercase">
                {state.projectName}/
              </Text>
              {files.map((f, i) => (
                <NavLink
                  key={f.filename}
                  label={f.filename}
                  leftSection={<IconFile size={14} />}
                  active={i === activeFile}
                  onClick={() => setActiveFile(i)}
                  py={4}
                  style={{ fontSize: 13 }}
                />
              ))}
            </Stack>
          </ScrollArea>
        </Paper>

        {/* Code preview */}
        <Paper
          withBorder
          style={{ flex: 1, overflow: 'hidden', alignSelf: 'stretch' }}
        >
          <Group
            justify="space-between"
            px="sm"
            py={6}
            style={{
              borderBottom: '1px solid var(--mantine-color-default-border)',
            }}
          >
            <Text size="xs" fw={500} c="dimmed">
              {currentFile.filename}
            </Text>
            <CopyButton value={currentFile.content} timeout={2000}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? '已複製！' : '複製程式碼'}>
                  <ActionIcon
                    size="sm"
                    variant="subtle"
                    color={copied ? 'teal' : 'gray'}
                    onClick={copy}
                  >
                    {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
                  </ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          </Group>
          <Editor
            height="450px"
            language={currentFile.language}
            value={currentFile.content}
            theme="vs-dark"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              padding: { top: 8 },
            }}
          />
        </Paper>
      </Group>

      {/* Download */}
      <Group justify="center">
        <Button
          size="lg"
          leftSection={<IconDownload size={20} />}
          loading={downloading}
          onClick={handleDownload}
        >
          下載 ZIP
        </Button>
      </Group>
    </Stack>
  );
}
