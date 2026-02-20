import { useState, useCallback } from 'react';
import {
  MantineProvider,
  Container,
  Stepper,
  Group,
  Button,
  Title,
  Text,
  Anchor,
  Stack,
  Box,
} from '@mantine/core';
import '@mantine/core/styles.css';
import { StepProject, StepStorage, StepModels, StepPreview } from '@/components/steps';
import { DEFAULT_WIZARD_STATE } from '@/types/wizard';
import type { WizardState } from '@/types/wizard';

const STEPS = [
  { label: '專案設定', description: '名稱、版本、Port' },
  { label: '儲存 & 設定', description: 'Storage、Naming、Encoding' },
  { label: 'Model 定義', description: '定義 Resource Models' },
  { label: '預覽 & 下載', description: '檢查程式碼並下載' },
];

function App() {
  const [active, setActive] = useState(0);
  const [state, setState] = useState<WizardState>(() => ({
    ...DEFAULT_WIZARD_STATE,
  }));

  const patchState = useCallback((patch: Partial<WizardState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  const nextStep = () => setActive((c) => Math.min(c + 1, STEPS.length - 1));
  const prevStep = () => setActive((c) => Math.max(c - 1, 0));

  return (
    <MantineProvider defaultColorScheme="dark">
      <Container size="lg" py="xl">
        {/* Header */}
        <Stack gap={4} mb="xl" align="center">
          <Title order={1}>AutoCRUD Starter Wizard</Title>
          <Text c="dimmed" size="sm">
            快速產生 AutoCRUD Python 專案模板 —{' '}
            <Anchor href="https://github.com/hychou/autocrud" target="_blank">
              autocrud
            </Anchor>
          </Text>
        </Stack>

        {/* Stepper */}
        <Stepper active={active} onStepClick={setActive} mb="xl">
          {STEPS.map((s, i) => (
            <Stepper.Step key={i} label={s.label} description={s.description} />
          ))}
        </Stepper>

        {/* Step content */}
        <Box mb="xl">
          {active === 0 && <StepProject state={state} onChange={patchState} />}
          {active === 1 && <StepStorage state={state} onChange={patchState} />}
          {active === 2 && <StepModels state={state} onChange={patchState} />}
          {active === 3 && <StepPreview state={state} />}
        </Box>

        {/* Navigation */}
        <Group justify="center" mt="xl">
          <Button variant="default" onClick={prevStep} disabled={active === 0}>
            上一步
          </Button>
          {active < STEPS.length - 1 && (
            <Button onClick={nextStep}>下一步</Button>
          )}
        </Group>
      </Container>
    </MantineProvider>
  );
}

export default App;
