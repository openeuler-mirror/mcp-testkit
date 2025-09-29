import asyncio
import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        description="MCP Server initialization args",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # gen-cases 子命令
    gen_parser = subparsers.add_parser('gen-cases', help='Generate test cases')
    gen_parser.add_argument(
        "--config", 
        type=str, 
        default="./mcp-servers-perf.json",
        help="Path to MCP Server config file"
    )
    
    #val-cases子命令
    val_parser = subparsers.add_parser('val-cases', help='Validate test cases')
    val_parser.add_argument(
        "--config", 
        type=str, 
        default="./mcp-servers-perf.json",
        help="Path to MCP Server config file"
    )
    val_parser.add_argument(
        "--testpath", 
        type=str, 
        default=".logs/perf_mcp_2025-09-12T06-43-29-026631/testcases.json",
        help="Path to get testcases"
    )

    # reporter 子命令
    rep_parser = subparsers.add_parser('rep-cases', help='report testing results')
    rep_parser.add_argument(
        "--valpath", 
        type=str, 
        default=".logs/perf_mcp_2025-09-11T07-31-04-418670/validation_results.json",
        help="Path to MCP Server config file"
    )
    
    return parser.parse_args()


async def gen_cases(config_path):
    from src.test_generator.TestGenerator import TestGenerator
    generator = TestGenerator(config_path=config_path)
    return await generator.run()
async def val_cases(config_path, testcase_path):
    from src.validator.Response_validator_withenv import ResponseValidator_withenv
    validator = ResponseValidator_withenv(config_path=config_path, testcase_path=testcase_path)
    return await validator.run()

async def main():
    args = parse_args()
    if args.command == 'gen-cases':
        await gen_cases(args.config)  
    if args.command == 'val-cases':
        await val_cases(args.config, args.testpath)

if __name__ == "__main__":
    asyncio.run(main())