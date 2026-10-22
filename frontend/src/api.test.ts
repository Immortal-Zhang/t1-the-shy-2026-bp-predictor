import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from './api';
import { buildRequest } from './domain';
import { analysisFixture, completeFixture, TEST_TIME } from './test/fixtures';

afterEach(() => vi.unstubAllGlobals());

describe('real API transport contract; fixtures only replace the transport in unit tests', () => {
  it('sends the pregame payload without postgame statistics or fallback probability', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(analysisFixture()), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    const payload = buildRequest(completeFixture());
    const response = await api.analyze(payload);
    expect(fetch).toHaveBeenCalledWith('/api/analyze', expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }));
    expect(response.prediction.model_version).toBe('SYNTHETIC_UNIT_TEST_ONLY');
  });
  it('surfaces model-unavailable 503 instead of a simulated result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'No trained model' }), { status: 503 })));
    await expect(api.analyze(buildRequest(completeFixture()))).rejects.toMatchObject({ status: 503, message: 'No trained model' });
  });
  it('surfaces field-validation errors and invalid response bodies', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ msg: 'Invalid champion' }] }), { status: 422 })).mockResolvedValueOnce(new Response('<html>upstream failure</html>', { status: 502 }));
    vi.stubGlobal('fetch', fetch);
    await expect(api.health()).rejects.toThrow('Invalid champion');
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
  });
  it('makes network failures explicit and preserves abort semantics', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error('network down')).mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'));
    vi.stubGlobal('fetch', fetch);
    await expect(api.health()).rejects.toMatchObject({ status: 0 });
    await expect(api.health()).rejects.toMatchObject({ name: 'AbortError' });
  });
  it('encodes professional IDs and as_of rather than dropping temporal context', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ players: [] }), { status: 200 })); vi.stubGlobal('fetch', fetch);
    await api.roster('oe:team:fixture', TEST_TIME);
    const url = fetch.mock.calls[0]![0] as string;
    expect(url).toContain('oe%3Ateam%3Afixture');
    expect(url).toContain('as_of=2026-10-22T00%3A00%3A00Z');
  });
});
