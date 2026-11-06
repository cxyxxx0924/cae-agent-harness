import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js'
import { zodToJsonSchema } from './schema'
import { importIgs, ImportIgsSchema, partitionAirbag, PartitionAirbagSchema, generateMesh, GenerateMeshSchema } from './tools/hypermesh'
import { solveLsDyna, SolveSchema } from './tools/lsdyna'
import { exportGif, ExportGifSchema } from './tools/hyperview'
import { generateReport, GenerateReportSchema } from './tools/report'

const server = new Server(
  { name: 'cae-mcp-server', version: '0.1.0' },
  {
    capabilities: {
      tools: {},
    },
  },
)

const TOOLS: { name: string; description: string; inputSchema: Record<string, unknown>; handler: (args: unknown, signal?: AbortSignal) => Promise<string> }[] = [
  {
    name: 'hypermesh_import_igs',
    description: 'Import an IGS or IGES geometry file into HyperMesh via hmbatch.exe. Returns the path of the created .hm model file.',
    inputSchema: zodToJsonSchema(ImportIgsSchema),
    handler: (args: unknown) => importIgs(ImportIgsSchema.parse(args)),
  },
  {
    name: 'hypermesh_partition_airbag',
    description: 'Partition the airbag model into cushion, inflator, and vent components in HyperMesh.',
    inputSchema: zodToJsonSchema(PartitionAirbagSchema),
    handler: (args: unknown) => partitionAirbag(PartitionAirbagSchema.parse(args)),
  },
  {
    name: 'hypermesh_generate_mesh',
    description: 'Generate quad/tria shell element mesh in HyperMesh, check quality, and export to LS-DYNA keyword format.',
    inputSchema: zodToJsonSchema(GenerateMeshSchema),
    handler: (args: unknown) => generateMesh(GenerateMeshSchema.parse(args)),
  },
  {
    name: 'lsdyna_solve',
    description: 'Run LS-DYNA using the configured backend: local software, local solver service, or server. In service mode, input and output paths belong to the solver service filesystem. Returns solver status, backend, progress, and output paths.',
    inputSchema: zodToJsonSchema(SolveSchema),
    handler: (args: unknown, signal?: AbortSignal) => solveLsDyna(SolveSchema.parse(args), signal),
  },
  {
    name: 'hyperview_export_gif',
    description: 'Open LS-DYNA result (d3plot) in HyperView and export an animated GIF showing the simulation.',
    inputSchema: zodToJsonSchema(ExportGifSchema),
    handler: (args: unknown) => exportGif(ExportGifSchema.parse(args)),
  },
  {
    name: 'generate_ppt_report',
    description: 'Generate a PowerPoint (.pptx) report containing the workflow steps, mesh stats, solver summary, and GIF animation.',
    inputSchema: zodToJsonSchema(GenerateReportSchema),
    handler: (args: unknown) => generateReport(GenerateReportSchema.parse(args)),
  },
]

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
}))

server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
  const tool = TOOLS.find(t => t.name === request.params.name)
  if (!tool) {
    return { content: [{ type: 'text', text: `Unknown tool: ${request.params.name}` }], isError: true }
  }
  try {
    const result = await tool.handler(request.params.arguments ?? {}, extra.signal)
    return { content: [{ type: 'text', text: result }] }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return { content: [{ type: 'text', text: message }], isError: true }
  }
})


async function main(): Promise<void> {
  const transport = new StdioServerTransport()
  await server.connect(transport)
  process.stderr.write('[cae-mcp-server] ready\n')
}

main().catch((err) => {
  process.stderr.write(`[cae-mcp-server] fatal: ${err instanceof Error ? err.message : String(err)}\n`)
  process.exit(1)
})
