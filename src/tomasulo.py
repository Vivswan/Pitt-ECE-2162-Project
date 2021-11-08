import copy
from typing import List

from src.component.computation_units.base_class import ComputationUnit
from src.component.computation_units.branch import Branch
from src.component.computation_units.float_adder import FloatAdder
from src.component.computation_units.float_multiplier import FloatMultiplier
from src.component.computation_units.integer_adder import IntegerAdder
from src.component.computation_units.memory import Memory
from src.component.instruction_buffer import InstructionBuffer
from src.component.intruction import Instruction
from src.component.registers.rat import RAT

num_register = 32
num_rob = 128
num_cbd = 1
count = 1


class Tomasulo:
    _cycle = 1

    def __init__(self, full_code):
        self.instruction_list: List[Instruction] = []
        self.instruction_buffer = InstructionBuffer()
        self.rat = RAT(num_register, num_register, num_rob)
        self.branch_unit = Branch(rat=self.rat, latency=3, num_rs=5)
        self.computational_units: List[ComputationUnit] = [
            IntegerAdder(rat=self.rat, latency=1, num_rs=5),
            FloatAdder(rat=self.rat, latency=3, num_rs=3),
            FloatMultiplier(rat=self.rat, latency=20, num_rs=2),
            Memory(rat=self.rat, latency=1, latency_mem=4, num_rs=3),
            self.branch_unit
        ]

        self.instruction_buffer.append_code(full_code)

    def issue(self):
        if self.rat.rob.is_full():
            return None

        if self.branch_unit.is_busy():
            return None

        for inst in self.instruction_buffer.history:
            if inst.type not in self.branch_unit.instruction_type:
                continue
            if "branch_correction" in inst.related_data and inst.related_data["branch_correction"]:
                self.instruction_buffer.pointer = inst.result
                # self.rat = inst.related_data["rat_copy"]
                del inst.related_data["branch_correction"]
                break

        instruction = self.instruction_buffer.pop()
        if instruction is None:
            return None

        # Makes a Copy of the RAT Table and stores it with the branch instruction
        instruction.related_data["rat_copy"] = copy.deepcopy(self.rat)

        # The predictions has been made on the outcome of the branch instruction.
        if instruction.type in self.branch_unit.instruction_type:
            self.instruction_buffer.pointer += self.branch_unit.branch_prediction(instruction)

        # this figures out which computational unit the instruction goes to.
        computational_unit = None
        for i in self.computational_units:
            if instruction.type in i.instruction_type:
                computational_unit = i
                break

        if computational_unit is None:
            Exception(f'"{instruction.type}" instruction has not been implemented by any computational unit')

        if computational_unit.is_full():
            return None

        computational_unit.decode_instruction(instruction)
        instruction.stage_event.issue = self._cycle
        computational_unit.issue_instruction(instruction)

    def execute(self):
        for i in self.computational_units:
            i.step(self._cycle)

    def write_back(self):
        compute_unit = []
        for i in self.computational_units:
            if i.has_result(self._cycle):
                for j in i.peak_result(self._cycle):
                    compute_unit.append((j.stage_event.execute[1], i, j))

        compute_unit.sort(key=lambda x: x[0])

        for i in compute_unit[:num_cbd]:
            instruction = i[2]
            i[1].remove_instruction(instruction)

            if instruction.destination == "NOP":
                continue

            rob_entry = self.rat.set_rob_value(instruction.destination, instruction.result)

            for instr in self.instruction_buffer.full_code:
                if rob_entry in instr.operands:
                    instr.operands[instr.operands.index(rob_entry)] = rob_entry.value

            instruction.stage_event.write_back = self._cycle

    def commit(self):
        instruction = None
        for instr in self.instruction_buffer.history:
            if instr.stage_event.commit is not None:
                if instr.stage_event.commit[1] >= self._cycle:
                    break
                else:
                    continue
            if instr.stage_event.write_back is not None:
                if instr.stage_event.write_back == "NOP":
                    instruction = instr
                elif instr.stage_event.write_back < self._cycle:
                    instruction = instr
                    self.rat.commit_rob(instr.destination)
            break

        if instruction is None:
            return None

        instruction.stage_event.commit = (self._cycle, self._cycle)

    def step(self):
        self.issue()
        self.execute()
        self.write_back()
        self.commit()
        self._cycle += 1

    def get_cycle(self) -> int:
        return self._cycle

    def is_working(self):
        # TODO
        return self.instruction_buffer.peak() is not None


if __name__ == '__main__':
    code = """
        ADD R1, R2, R3 
        SUB R1, R1, R3 
        ADDI R1, R2, 5
        ADDD F1, F2, F3 
        SUB.D F1, F2, F3 
        SUBi R1, R2, 5

        LD R1 0(R2) 
        LD R1 0(R2) 
        LD R1 0(R2) 
        # ADDI R1, R2, 5
        SD R1 8(R2) 
        ADDI R1, R2, 5
        LD R1 8(R2) 
        LD R1 8(R2) 
        # BEQ R1, R2, 2
        # BNE R1, R2, 
    """
    tomasulo = Tomasulo(code)
    while tomasulo._cycle < 500:
        tomasulo.step()
    print()
    for k in tomasulo.instruction_buffer.history:
        print(k)
    print()
    # tomasulo.rat.print_tables()
